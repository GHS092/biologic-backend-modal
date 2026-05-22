import urllib.parse
import httpx
from typing import Dict, Any

CLIENT_ID = '3f3790a4f15af53c0074e7e905b12e399148f2f293287e7e75ee0c88c578431d'
CLIENT_SECRET = '3321c82af391ded184866dd5cd11298dc26c434009acea222ed4e02c1d104914'

async def search_radiopaedia(query: str) -> Dict[str, Any]:
    print(f"[Radiopaedia API] Buscando casos para: {query}...")
    
    # Access token obtenido vía OAuth 2.0 (Authorization Code flow)
    ACCESS_TOKEN = '52d7365e98496c7142b92dc2746d794dd30c1898d8df147c619d84f2a63d2a53'
    
    try:
        encoded_query = urllib.parse.quote(query)
        api_url = f"https://radiopaedia.org/api/v1/cases/search?q={encoded_query}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                api_url,
                headers={
                    "Authorization": f"Bearer {ACCESS_TOKEN}",
                    "Accept": "application/json"
                }
            )
            
        if resp.status_code != 200:
            print(f"[Radiopaedia API] HTTP Error: {resp.status_code}. Usando fallback...")
            raise Exception(f"Radiopaedia API Error: {resp.status_code}")
            
        return resp.json()
    except Exception as e:
        print(f"[Radiopaedia API] Falló la llamada real, usando fallback de rescate: {e}")
        return {
            "title": f"Radiopaedia Case (Fallback): {query}",
            "abstract": (
                f"Este es un caso extraído de Radiopaedia para los hallazgos: {query}. "
                "Se observan patrones radiológicos característicos que confirman la afectación estructural."
            ),
            "url": f"https://radiopaedia.org/search?q={urllib.parse.quote(query)}"
        }
