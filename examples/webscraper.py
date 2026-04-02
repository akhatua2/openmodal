"""A simple web scraper — demonstrates f.remote() with args and f.map()."""

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
