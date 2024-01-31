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
from time import sleep
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


def _are_same_urls(url1: str, url2: str) -> bool:
    """Checks whether two URLs refer to the same resource."""
    parsed1 = urllib.parse.urlparse(url1)
    parsed2 = urllib.parse.urlparse(url2)
    url1_no_scheme = parsed1._replace(scheme="").geturl()
    url2_no_scheme = parsed2._replace(scheme="").geturl()
    return url1_no_scheme == url2_no_scheme


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
    download_pdf_button = sopa.find(
        "button", {"onclick": lambda x: "location.href" in x}
    )
    if download_pdf_button is None:
        # TODO: This could happen in other conditions. For example, if no
        # button is found
        raise CaptchaRequiredException("SciHub asked for CAPTCHA")
    pdf_link = download_pdf_button["onclick"].split("'")[1]
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

    def __init__(
        self, base_url: Optional[str] = None, max_tries: int = 3
    ) -> None:
        self.sess = requests.Session()
        self.sess.headers = HEADERS
        self.available_base_url_list = self._get_available_scihub_urls()
        self.max_tries = max_tries
        self._response: Optional[requests.Response] = None
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
            raise OutOfMirrorsException("Ran out of valid sci-hub urls")
        if not _are_same_urls(self.base_url, self.available_base_url_list[0]):
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
        if self._response is None:
            pdf_link = self.fetch(reference)
        else:
            pdf_link = _extract_pdf_link(self._response)
        _download_pdf(pdf_link, output_dir, pdf_filename)

    def fetch(self, reference: str) -> str:
        """Fetches the link to a PDF file via Sci-Hub.

        Args:
            reference (str): Reference string you would put on Sci-Hub. Can be a paywalled URL, PMID or DOI.

        Returns:
            str: Link for direct download of the document. I will be empty if the article could not be found.
        """
        try_ = 1
        while True:
            if try_ >= self.max_tries:
                logger.info(
                    "{} failed after {} tries.", self.base_url, self.max_tries
                )
                self._change_base_url()
                try_ = 1
            self._response = requests.post(
                url=self.base_url, data={"request": reference}
            )
            if len(self._response.content) == 0:
                logger.warning("{} gave an empty response. Retrying in 3s.")
                sleep(3)
                try_ += 1
                continue
            try:
                pdf_link = _extract_pdf_link(self._response)
            except CaptchaRequiredException:
                logger.info(
                    "{} asked for CAPTCHA. Retrying with another mirror",
                    self.base_url,
                )
                self._change_base_url()
                continue
            break
        return pdf_link


class OutOfMirrorsException(Exception):
    """
    Invoked if SciHub object runs out of mirrors to try
    """

    pass


class CaptchaRequiredException(Exception):
    # TODO: implement this
    pass
