# -*- coding: utf-8 -*-

"""
Sci-API Unofficial API
[Search|Download] research papers from [scholar.google.com|sci-hub.io].

@author zaytoun
@author ezxpro
@author dmunozg
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Union

import requests
import urllib3
from bs4 import BeautifulSoup
from loguru import logger
from retrying import retry

# log config
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time}</green> <level>{message}</level>",
    colorize=True,
    level="DEBUG",
)
urllib3.disable_warnings()

# constants
SCHOLARS_BASE_URL: str = "https://scholar.google.com/scholar"
HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0"
}


class SciHub(object):
    """
    SciHub class can search for papers on Google Scholars
    and fetch/download papers from sci-hub.io
    """

    def __init__(self) -> None:
        self.sess = requests.Session()
        self.sess.headers = HEADERS
        self.available_base_url_list = self._get_available_scihub_urls()
        self.base_url = self.available_base_url_list[0] + "/"

    def _get_available_scihub_urls(self) -> list[str]:
        """
        Finds available scihub urls via https://sci-hub.now.sh/
        """
        urls = []
        res = requests.get("https://sci-hub.now.sh/")
        s = self._get_soup(res.content.decode("utf-8"))
        for a in s.find_all("a", href=True):
            if "sci-hub." in a["href"]:
                urls.append(a["href"])
        return urls

    def _get_soup(self, html: str) -> BeautifulSoup:
        """
        Return html soup.
        """
        return BeautifulSoup(html, "html.parser")

    def set_proxy(self, proxy: dict[str, str]) -> None:
        """Set a proxy for the request session.

        Args:
            proxy (dict[str, str]): dict containing http and https proxies.
        """
        self.sess.proxies.update(proxy)

    def _change_base_url(self) -> None:
        if not self.available_base_url_list:
            raise Exception("Ran out of valid sci-hub urls")
        del self.available_base_url_list[0]
        self.base_url = self.available_base_url_list[0] + "/"
        logger.info(
            "I'm changing to {}".format(self.available_base_url_list[0])
        )

    def search(
        self, query: str, limit: int = 5, **kwargs: Any
    ) -> dict[str, Union[list[dict[str, str]], str]]:
        """
        Performs a query on scholar.google.com, and returns a dictionary
        of results in the form {'papers': ...}. Unfortunately, as of now,
        captchas can potentially prevent searches after a certain limit.
        """
        start: int = 0
        results: dict[str, Union[list[dict[str, str]], str]] = {}
        results.setdefault("papers", [])
        papers_found: list[dict[str, str]] = []

        while True:
            try:
                res = self.sess.get(
                    SCHOLARS_BASE_URL, params={"q": query, "start": start}
                )
            except requests.exceptions.RequestException as e:
                results["err"] = (
                    "Failed to complete search with query %s (connection error)"
                    % query
                )
                return results

            s = self._get_soup(res.content.decode("utf-8"))
            papers = s.find_all("div", class_="gs_r")

            if not papers:
                if "CAPTCHA" in str(res.content):
                    results["err"] = (
                        "Failed to complete search with query %s (captcha)"
                        % query
                    )
                return results

            for paper in papers:
                if not paper.find("table"):
                    source = None
                    pdf = paper.find("div", class_="gs_ggs gs_fl")
                    link = paper.find("h3", class_="gs_rt")

                    if pdf:
                        source = pdf.find("a")["href"]
                    elif link.find("a"):
                        source = link.find("a")["href"]
                    else:
                        continue

                    papers_found.append({
                        "name": link.text,
                        "url": source,
                    })

                    if len(papers_found) >= limit:
                        results["papers"] = papers_found
                        return results

            start += 10

    @retry(
        wait_random_min=100, wait_random_max=1000, stop_max_attempt_number=10
    )
    def download(
        self, identifier: str, destination: str = "", path=None
    ) -> dict[str, str | bytes]:
        """
        Downloads a paper from sci-hub given an indentifier (DOI, PMID, URL).
        Currently, this can potentially be blocked by a captcha if a certain
        limit has been reached.
        """
        data = self.fetch(identifier)

        if "err" not in data:
            self._save(data["pdf"], os.path.join(destination, path))

        return data

    def fetch(self, identifier: str) -> Union[dict[str, str | bytes], None]:
        """
        Fetches the paper by first retrieving the direct link to the pdf.
        If the indentifier is a DOI, PMID, or URL pay-wall, then use Sci-Hub
        to access and download paper. Otherwise, just download paper directly.
        """

        try:
            url = self._get_direct_url(identifier)

            # verify=False is dangerous but sci-hub.io
            # requires intermediate certificates to verify
            # and requests doesn't know how to download them.
            # as a hacky fix, you can add them to your store
            # and verifying would work. will fix this later.
            res = self.sess.get(url, verify=False)

            if res.headers["Content-Type"] != "application/pdf":
                self._change_base_url()
                logger.info(
                    "Failed to fetch pdf with identifier %s "
                    "(resolved url %s) due to captcha" % (identifier, url)
                )
                raise CaptchaNeedException(
                    "Failed to fetch pdf with identifier %s "
                    "(resolved url %s) due to captcha" % (identifier, url)
                )
            else:
                return {"pdf": res.content, "url": url}

        except requests.exceptions.ConnectionError:
            logger.info(
                "Cannot access {}, changing url".format(
                    self.available_base_url_list[0]
                )
            )
            self._change_base_url()
            return None
        except requests.exceptions.RequestException as e:
            logger.info(
                "Failed to fetch pdf with identifier %s (resolved url %s) due to request exception."
                % (identifier, url)
            )
            return {
                "err": "Failed to fetch pdf with identifier %s (resolved url %s) due to request exception."
                % (identifier, url)
            }

    def _get_direct_url(self, identifier: str) -> str:
        """
        Finds the direct source url for a given identifier.
        """
        id_type = self._classify(identifier)
        logger.debug("URL classified as {}", id_type)
        return (
            identifier
            if id_type == "url-direct"
            else self._search_direct_url(identifier)
        )

    def _search_direct_url(self, identifier: str) -> Union[str, None]:
        """
        Sci-Hub embeds papers in an iframe. This function finds the actual
        source url which looks something like https://moscow.sci-hub.io/.../....pdf.
        """
        res = self.sess.get(self.base_url + identifier, verify=False)
        s = self._get_soup(res.content)
        iframe = s.find("iframe")
        if iframe:
            return (
                iframe.get("src")
                if not iframe.get("src").startswith("//")
                else "http:" + iframe.get("src")
            )
        else:
            return None

    def _classify(self, identifier: str) -> str:
        """
        Classify the type of identifier:
        url-direct - openly accessible paper
        url-non-direct - pay-walled paper
        pmid - PubMed ID
        doi - digital object identifier
        """
        # TODO: rework this and classify with regex
        if identifier.startswith("http") or identifier.startswith("https"):
            if identifier.endswith("pdf"):
                return "url-direct"
            else:
                return "url-non-direct"
        elif identifier.isdigit():
            return "pmid"
        else:
            return "doi"

    def _save(self, data: bytes, path: str | Path) -> None:
        """
        Save a file give data and a path.
        """
        with open(path, "wb") as f:
            f.write(data)

    def _generate_name(self, res: Any, title: str) -> str:
        """
        Generate unique filename for paper. Returns the title passed in.
        """
        # TODO: This function does nothing?
        return title


class CaptchaNeedException(Exception):
    pass


# TODO: Move this to its own file
def main() -> None:
    sh = SciHub()

    parser = argparse.ArgumentParser(
        description="SciHub - To remove all barriers in the way of science."
    )
    parser.add_argument(
        "-d",
        "--download",
        metavar="(DOI|PMID|URL)",
        help="tries to find and download the paper",
        type=str,
    )
    parser.add_argument(
        "-f",
        "--file",
        metavar="path",
        help="pass file with list of identifiers and download each",
        type=str,
    )
    parser.add_argument(
        "-s",
        "--search",
        metavar="query",
        help="search Google Scholars",
        type=str,
    )
    parser.add_argument(
        "-sd",
        "--search_download",
        metavar="query",
        help="search Google Scholars and download if possible",
        type=str,
    )
    parser.add_argument(
        "-l",
        "--limit",
        metavar="N",
        help="the number of search results to limit to",
        default=10,
        type=int,
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="path",
        help="directory to store papers",
        default="",
        type=str,
    )
    parser.add_argument(
        "-p",
        "--proxy",
        help="via proxy format like socks5://user:pass@host:port",
        action="store",
        type=str,
    )

    args = parser.parse_args()

    if args.proxy:
        sh.set_proxy(args.proxy)

    if args.download:
        result = sh.download(args.download, args.output, title=args.download)
        if "err" in result:
            logger.debug("%s", result["err"])
        else:
            logger.debug(
                "Successfully downloaded file with identifier %s",
                args.download,
            )
    elif args.search:
        results = sh.search(args.search, args.limit)
        if "err" in results:
            logger.debug("%s", results["err"])
        else:
            logger.debug(
                "Successfully completed search with query %s", args.search
            )
        print(results)
    elif args.search_download:
        results = sh.search(args.search_download, args.limit)
        if "err" in results:
            logger.debug("%s", results["err"])
        else:
            logger.debug(
                "Successfully completed search with query %s",
                args.search_download,
            )
            for paper in results["papers"]:
                result = sh.download(paper["url"], args.output)
                if "err" in result:
                    logger.debug("%s", result["err"])
                else:
                    logger.debug(
                        "Successfully downloaded file with identifier %s",
                        paper["url"],
                    )
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
            for line in lines:
                identifier, title = line.split(",", 1)
                filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", title)
                filename += ".pdf"
                result = sh.download(identifier, args.output, path=filename)
                if "err" in result:
                    logger.debug("%s", result["err"])
                else:
                    logger.debug(
                        "Successfully downloaded file with identifier %s",
                        identifier,
                    )
                    # Remove any characters from the identifier that are not allowed in filenames
                    filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", title)
                    # If the filename is empty after stripping, use a sanitized version of the identifier as the filename
                    if not filename:
                        filename = re.sub(
                            r'[<>:"/\\|?*\x00-\x1F]', "", identifier
                        )
                    # Add .PDF extension to the filename
                    filename += ".pdf"
                    # Pass the filename to the download method
                    print(f"Downloading {filename}...")
                    sh.download(identifier, args.output, path=filename)


if __name__ == "__main__":
    main()
