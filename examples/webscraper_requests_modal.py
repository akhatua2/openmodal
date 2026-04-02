"""Web scraper with requests + BeautifulSoup — Modal version for comparison."""

import modal

app = modal.App("example-webscraper-requests")

scraper_image = modal.Image.debian_slim(python_version="3.12").pip_install("requests", "beautifulsoup4")


@app.function(image=scraper_image)
async def get_links(url: str) -> list[str]:
    import asyncio
    import requests
    from bs4 import BeautifulSoup

    resp = await asyncio.to_thread(requests.get, url, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    return [a["href"] for a in soup.find_all("a", href=True)]


@app.local_entrypoint()
def main():
    urls = ["http://example.com", "http://modal.com"]
    for links in get_links.map(urls):
        for link in links:
            print(link)
