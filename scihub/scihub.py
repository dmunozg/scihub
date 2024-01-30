# -*- coding: utf-8 -*-

"""
Sci-API Unofficial API
[Search|Download] research papers from [scholar.google.com|sci-hub.io].

@author zaytoun
@author ezxpro
@author dmunozg
"""

import sys
from pathlib import Path
from typing import Any, MutableMapping, Union, Optional

import requests
import urllib
from bs4 import BeautifulSoup
from loguru import logger

# TODO: "retrying" is no longer being maintained. Should be replaced
# with backoff
# from retrying import retry

# log config
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time}</green> <level>{message}</level>",
    colorize=True,
    level="DEBUG",
)

# constants
SCHOLARS_BASE_URL: str = "https://scholar.google.com/scholar"
HEADERS: MutableMapping[str, str | bytes] = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0"
}


def _extract_pdf_link(response: requests.Response) -> str:
    """
    Extracts the PDF link from a given HTTP response.

    This function takes a requests.Response object as input and returns
    the URL to the corresponding PDF document. The assumption is that
    the PDF link can be found within a 'button' tag with a specific attribute
    and the URL will be in the "onclick" HTML attribute of this button. This
    is the case for Sci-Hub found references.

    Usage:
        pdf_url = extract_pdf_link(requests.Response())"""
    sopa = BeautifulSoup(response.content, "html.parser")
    # TODO: This should verify if the response is facing a Captcha.
    pdf_link = sopa.find(
        "button", {"onclick": lambda x: "location.href" in x}
    )["onclick"].split("'")[1]
    return pdf_link.replace("//", "http://")


def _download_pdf(
    pdf_link: str, output_dir: str | Path, pdf_filename: Optional[str] = None
) -> None:
    """
    Downloads a PDF file from a provided link and saves it in the specifie
    directory. If no filename is provided, it will take the filename from the
    original link.

    Parameters
    - pdf_link (str): The URL of the PDF to be downloaded.
    - output_dir (str | Path): The directory where the file will be saved.
    - pdf_filename (Optional[str], optional): A specific filename for the PDF.
    Default is None.

    Returns
    - None: As this function does not directly return a value, it operates by
    changing the state of the program. It downloads the specified PDF and
    saves it to the specified directory."""
    if pdf_filename is None:
        target_path = Path(urllib.parse.urlparse(pdf_link).path)
        pdf_target_filename = Path(output_dir) / target_path.parts[-1]
    else:
        pdf_target_filename = Path(output_dir) / pdf_filename
    response = requests.get(pdf_link)
    if response.status_code == 200:
        logger.info(
            "PDF found successfully. Saving to {}", pdf_target_filename
        )
        with open(pdf_target_filename, "wb") as output_handler:
            output_handler.write(response.content)
    else:
        logger.error(
            "Failed to download the PDF file. Status code: {}",
            response.status_code,
            response.status_code,
        )


class SciHub(object):
    """
    SciHub class can fetch/download papers from Sci-Hub
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.sess = requests.Session()
        self.sess.headers = HEADERS
        self.available_base_url_list = self._get_available_scihub_urls()
        if base_url is None:
            self.base_url = self.available_base_url_list[0] + "/"
        else:
            self.base_url = base_url

    def _get_available_scihub_urls(self) -> list[str]:
        """
        Finds available Sci-Hub URLs via https://sci-hub.now.sh/.
        This method retrieves a list of working Sci-Hub instance URLs by accessing the
        provided link and parsing the resulting HTML page for relevant links.
        Returns:
            A list of available Sci-Hub URLs as strings.
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
        """Update the current base URL by choosing a new one from the available
        base URL list.
        Raises:
            Exception: If there are no valid base URLs left in the list.
        """
        if not self.available_base_url_list:
            raise Exception("Ran out of valid sci-hub urls")
        del self.available_base_url_list[0]
        self.base_url = self.available_base_url_list[0] + "/"
        logger.info("Changing base_url to {}", self.base_url)

    # TODO: This should be replaced with with scholarly
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

    def download(
        self,
        reference: str,
        output_dir: str | Path,
        pdf_filename: Optional[str] = None,
    ) -> None:
        """Downloads the PDF of a reference from SciHub.

        Args:
            reference (str): Reference string you would pun on Sci-hub.
            output_dir (str | Path): Directory where the pdf will be saved
            pdf_filename (str, Optional): Name of the PDF file that will be saved.
              By default, will choose the name given by Sci-Hub.
        """
        pdf_link = self.fetch(reference)
        _download_pdf(pdf_link, output_dir, pdf_filename)

    def fetch(self, reference: str) -> str:
        """Fetches the link to a PDF file via Sci-Hub.

        Args:
            reference (str): Reference string you would put on Sci-Hub. Can be a paywalled URL, PMID or DOI.

        Returns:
            str: Link for direct download of the document. I will be empty if the article could not be found.
        """
        response = requests.post(
            url=self.base_url, data={"request": reference}
        )
        return _extract_pdf_link(response)


class CaptchaNeedException(Exception):
    # TODO: implement this
    pass
