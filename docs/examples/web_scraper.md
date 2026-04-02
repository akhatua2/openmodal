# Web scraper

This example shows how to build a distributed web scraper with OpenModal,
progressing from a simple local script to parallel remote execution with
custom container images.

## Step 1: Scrape links locally

Start with plain Python:

```python
import re
import urllib.request

def get_links(url):
    response = urllib.request.urlopen(url)
    html = response.read().decode("utf8")
    links = []
    for match in re.finditer('href="(.*?)"', html):
        links.append(match.group(1))
    return links

if __name__ == "__main__":
    print(get_links("http://example.com"))
```

```bash
python webscraper.py
# ['https://www.iana.org/domains/example']
```

## Step 2: Run it remotely

Add OpenModal — the only changes are the import, the decorator, and the entrypoint:

```python
import re
import urllib.request
import openmodal

app = openmodal.App(name="example-webscraper")

@app.function()
def get_links(url):
    response = urllib.request.urlopen(url)
    html = response.read().decode("utf8")
    links = []
    for match in re.finditer('href="(.*?)"', html):
        links.append(match.group(1))
    return links

@app.local_entrypoint()
def main(url: str = "http://example.com"):
    links = get_links.remote(url)
    print(links)
```

```bash
openmodal run examples/webscraper.py --url http://example.com
```

```
✓ Initialized.
✓ Created objects.
['https://iana.org/domains/example']
✓ App completed.
```

The function ran on a GCE container, not on your machine.

## Step 3: Add dependencies with a custom image

Use `requests` and `beautifulsoup4` for better HTML parsing.
Define a custom container image with the dependencies:

```python
import openmodal

app = openmodal.App("example-webscraper-requests")

scraper_image = openmodal.Image.debian_slim().pip_install("requests", "beautifulsoup4")

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
```

```bash
openmodal run examples/webscraper_requests.py
```

The first run builds the Docker image (takes ~2 minutes). Subsequent runs
use the cached image and start much faster.

## What this demonstrates

| Feature | How it's used |
|---|---|
| `f.remote(url)` | Run a single function call on GCP |
| `f.map(urls)` | Run multiple calls in parallel |
| `Image.debian_slim()` | Base container image with Python |
| `.pip_install(...)` | Add Python packages to the image |
| `async def` | Async functions work transparently |
| CLI args (`--url`) | Entrypoint parameters become CLI flags |
