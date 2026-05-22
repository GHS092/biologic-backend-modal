import os
import re
import xml.etree.ElementTree as ET
import httpx
import asyncio
from typing import List, Dict, Any, Optional

NCBI_API_KEYS = [
    os.environ.get("PUBMED_API_KEY_1", "6f014e219c23049446633329f34774ae3407"),
    os.environ.get("PUBMED_API_KEY_2", "83562de39c035e40e4f2a268b3e34d01e008")
]
NCBI_API_KEYS = [k for k in NCBI_API_KEYS if k]
current_key_index = 0

def get_next_api_key() -> Optional[str]:
    global current_key_index
    if not NCBI_API_KEYS:
        return None
    key = NCBI_API_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(NCBI_API_KEYS)
    return key

def clean_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]*>?", "", text)

async def search_europe_pmc(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    try:
        # Sanitize query
        safe_query = re.sub(r"[^\w\s\u00C0-\u024F-]", " ", query).strip()
        words = safe_query.split()
        safe_query = " ".join(words[:8])
        
        if not safe_query:
            return []
            
        epmc_query = f'{safe_query} AND (OPEN_ACCESS:"Y" OR IN_EPMC:"Y")'
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": epmc_query,
            "format": "json",
            "resultType": "core",
            "pageSize": str(max_results)
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            
        if resp.status_code != 200:
            print(f"[EuropePMC] Error HTTP {resp.status_code}")
            return []
            
        data = resp.json()
        results = data.get("resultList", {}).get("result", [])
        
        articles = []
        for item in results:
            abstract = clean_html(item.get("abstractText", ""))
            
            full_text_url = None
            full_text_list = item.get("fullTextUrlList", {}).get("fullTextUrl", [])
            for u in full_text_list:
                if u.get("documentStyle") in ("html", "doi"):
                    full_text_url = u.get("url")
                    break
                    
            articles.append({
                "id": item.get("pmcid") or item.get("pmid") or item.get("id") or "",
                "title": item.get("title", ""),
                "authors": item.get("authorString", ""),
                "abstract": abstract,
                "pubDate": item.get("firstPublicationDate") or item.get("pubYear") or "",
                "source": item.get("journalTitle") or item.get("bookOrReportDetails", {}).get("publisher") or "",
                "fullTextUrl": full_text_url,
                "isOpenAccess": item.get("isOpenAccess") == "Y"
            })
        return articles
    except Exception as e:
        print(f"[EuropePMC] Fallo en la búsqueda para '{query}': {e}")
        return []

async def get_full_text_sections(pmcid: str) -> Dict[str, str]:
    if not pmcid or not pmcid.startswith("PMC"):
        return {"results": "", "conclusion": ""}
    try:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            
        if resp.status_code != 200:
            return {"results": "", "conclusion": ""}
            
        xml_text = resp.text
        
        results_match = re.search(r'<sec[^>]*sec-type="results"[^>]*>([\s\S]*?)<\/sec>', xml_text, re.IGNORECASE)
        conclusion_match = re.search(r'<sec[^>]*sec-type="conclusions"[^>]*>([\s\S]*?)<\/sec>', xml_text, re.IGNORECASE)
        
        results = clean_html(results_match.group(1)).strip() if results_match else ""
        conclusion = clean_html(conclusion_match.group(1)).strip() if conclusion_match else ""
        
        if len(results) > 5000:
            results = results[:5000] + "..."
        if len(conclusion) > 3000:
            conclusion = conclusion[:3000] + "..."
            
        return {"results": results, "conclusion": conclusion}
    except Exception as e:
        print(f"[EuropePMC FullText] Error obteniendo XML para {pmcid}: {e}")
        return {"results": "", "conclusion": ""}

async def search_pubmed(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    # 1. Sanitize query: Remove special characters, restrict to 6 words max to prevent combinatorial timeouts
    safe_query = re.sub(r"[^\w\s-]", " ", query).strip()
    words = safe_query.split()
    safe_query = " ".join(words[:6])
    
    if not safe_query:
        return []
        
    errors = []
    
    # --- STRATEGY 1: Europe PMC (Fastest, JSON native, CORS friendly) ---
    try:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": safe_query,
            "format": "json",
            "resultType": "core",
            "pageSize": str(max_results)
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("resultList", {}).get("result", [])
            if results:
                mapped = []
                for item in results:
                    mapped.append({
                        "id": item.get("pmid") or item.get("id") or "",
                        "title": item.get("title", ""),
                        "authors": item.get("authorString", ""),
                        "abstract": clean_html(item.get("abstractText", "")),
                        "pubDate": item.get("firstPublicationDate") or item.get("pubYear") or "",
                        "source": item.get("journalTitle") or item.get("bookOrReportDetails", {}).get("publisher") or ""
                    })
                return mapped
        else:
            errors.append(f"EuropePMC status: {resp.status_code}")
    except Exception as e:
        errors.append(f"EuropePMC failed: {e}")
        
    # --- STRATEGY 2: NCBI E-utilities Fallback ---
    try:
        api_key = get_next_api_key()
        api_key_param = {"api_key": api_key} if api_key else {}
        
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": safe_query,
            "retmode": "json",
            "retmax": str(max_results),
            **api_key_param
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            search_resp = await client.get(search_url, params=params)
            
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            ids = search_data.get("esearchresult", {}).get("idlist", [])
            
            if ids:
                fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(ids),
                    "retmode": "xml",
                    **api_key_param
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    fetch_resp = await client.get(fetch_url, params=fetch_params)
                    
                if fetch_resp.status_code == 200:
                    xml_text = fetch_resp.text
                    root = ET.fromstring(xml_text)
                    articles = []
                    
                    for pubmed_article in root.findall(".//PubmedArticle"):
                        pmid_el = pubmed_article.find(".//PMID")
                        pmid = pmid_el.text if pmid_el is not None else ""
                        
                        title_el = pubmed_article.find(".//ArticleTitle")
                        title = title_el.text if title_el is not None else ""
                        
                        abstract_parts = []
                        for abstract_text in pubmed_article.findall(".//AbstractText"):
                            label = abstract_text.attrib.get("Label")
                            if label:
                                abstract_parts.append(f"{label}: {abstract_text.text or ''}")
                            else:
                                abstract_parts.append(abstract_text.text or "")
                        abstract = "\n".join(abstract_parts).strip()
                        
                        authors_list = []
                        for author in pubmed_article.findall(".//Author"):
                            last_name_el = author.find("LastName")
                            initials_el = author.find("Initials")
                            last_name = last_name_el.text if last_name_el is not None else ""
                            initials = initials_el.text if initials_el is not None else ""
                            if last_name:
                                authors_list.append(f"{last_name} {initials}".strip())
                        authors = ", ".join(authors_list)
                        
                        year_el = pubmed_article.find(".//JournalIssue/PubDate/Year")
                        month_el = pubmed_article.find(".//JournalIssue/PubDate/Month")
                        year = year_el.text if year_el is not None else ""
                        month = month_el.text if month_el is not None else ""
                        pub_date = f"{year} {month}".strip()
                        
                        source_el = pubmed_article.find(".//Journal/Title")
                        source = source_el.text if source_el is not None else ""
                        
                        articles.append({
                            "id": pmid,
                            "title": title,
                            "authors": authors,
                            "abstract": abstract,
                            "pubDate": pub_date,
                            "source": source
                        })
                    return articles
    except Exception as e:
        errors.append(f"NCBI failed: {e}")
        
    print(f"[High-Availability Search] All endpoints failed for query '{safe_query}'. Errors: {errors}")
    return []
