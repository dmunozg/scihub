import argparse
import os
from pathlib import Path
from sys import exit
from typing import Optional

from .scihub import SciHub


def main(
    reference: str,
    output_pdf: Optional[str | Path] = None,
    sci_hub_url: Optional[str] = None,
) -> int:
    # TODO: validate the given arguments
    sh = SciHub(sci_hub_url)
    if output_pdf is None:
        output_dir = Path(os.getcwd())
        pdf_filename = None
    else:
        output_dir = Path(output_pdf).parent
        pdf_filename = Path(output_pdf).parts[-1]
    sh.download(
        reference=reference, output_dir=output_dir, pdf_filename=pdf_filename
    )
    return 0


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Downloads the PDF of an article from Sci-Hub."
    )
    parser.add_argument(
        "reference",
        type=str,
        help="Reference string to be sent to Sci-Hub. Can be a paywalled URL, a PMID or a DOI",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Filename where the PDF will be saved to. Will use the name given by Sci-Hub by default.",
    )
    parser.add_argument(
        "--sci-hub-url",
        type=str,
        help="Sci-Hub URL to employ when obtaining the PDF. Will get one from sci-hub.now.sh by default.",
    )
    args = parser.parse_args()
    exit(
        main(
            reference=args.reference,
            output_pdf=args.output,
            sci_hub_url=args.sci_hub_url,
        )
    )
