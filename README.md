Sci-Hub lib
[![Python](https://img.shields.io/badge/Python-3%2B-blue.svg)](https://www.python.org)
=======

Forked from [Scihub Downloader](https://github.com/ezxpro/scihub-downloader) which is a fork of [scihub.py](https://github.com/zaytoun/scihub.py).

Usage
-----

First, import the module and create an instance of the `SciHub` object. At this point, you can optionally specify which Sci-Hub mirror will be employed.

```python
from scihub import SciHub

sh = SciHub(base_url="https://sci-hub.ru")
```

The `fetch` method will obtain a URL for direct downloading of an specified reference:

```python
sh.fetch("https://doi.org/10.1111/gwmr.12285")
```

<pre>> 'http://dacemirror.sci-hub.ru/journal-article/0b1ec328b87368b809e0913c8591b9bc/miller2018.pdf?download=true'</pre>

The `download` method will automatically download the PDF from the reference into a specified location:

```python
sh.download(
    reference="https://doi.org/10.1111/gwmr.12285",
    output_dir="./",
    pdf_filename = "paper.pdf" # This is optional
  )
```

CLI tool
--------

The package features a tool to download PDF files from the command line.

```bash
scihub "https://doi.org/10.1111/gwmr.12285"
```

It can be called with the arguments `--output`/`-o` to specify where to save the PDF file, and with `--sci-hub-url` to specify the Sci-Hub mirror.

```bash
scihub "https://doi.org/10.1111/gwmr.12285" -o here.pdf --sci-hub-url "https://sci-hub.ru"
```

License
-------

MIT
