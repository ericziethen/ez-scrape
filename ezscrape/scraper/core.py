#!/usr/bin/env python3

"""Module providing core definitions for scraper functionality."""

import enum
import logging
import sys

from typing import Iterator, List

import fake_useragent
import scraper.exceptions as exceptions

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

DEFAULT_REQUEST_TIMEOUT = 5.0
DEFAULT_NEXT_PAGE_TIMEOUT = 3
DEFAULT_JAVASCRIPT_WAIT = 3.0
DEFAULT_MAX_PAGES = 15


@enum.unique
class ScrapeStatus(enum.Enum):
    """Enum for the Download Status."""

    # pylint: disable=invalid-name
    UNKNOWN = 'Unknown'
    TIMEOUT = 'Timeout'
    SUCCESS = 'Success'
    ERROR = 'Error'
    PROXY_ERROR = 'Proxy Error'


class ScrapeConfig():
    """Class to hold scrape config data needed for downloading the html."""

    def __init__(self, url: str):
        """Initialize a default scrape config with the given url."""
        # TODO - CHeck if can Simplify some parameters
        # TODO - it should be clear how to configure
        # TODO - Maybe Multipage, Javascript & xpath should be part of constructor???
        self.url = url
        self.request_timeout = DEFAULT_REQUEST_TIMEOUT
        self.proxy_http = ''
        self.proxy_https = ''
        self.javascript = False
        self.javascript_wait = DEFAULT_JAVASCRIPT_WAIT
        self.useragent = None
        self.attempt_multi_page = False
        self.wait_for_xpath = ''
        self.max_pages = DEFAULT_MAX_PAGES
        self.next_page_timeout = DEFAULT_NEXT_PAGE_TIMEOUT

    @property
    def url(self) -> str:
        """Property to define the Url attribute."""
        return self._url

    @url.setter
    def url(self, new_url: str) -> None:
        """Setter for the Url attribute."""
        if (not new_url) or (not isinstance(new_url, str)):
            raise exceptions.ScrapeConfigError('Url cannot be blank')
        self._url = new_url  # pylint: disable=attribute-defined-outside-init


class ScrapePage():
    """Class to represent a single scraped page."""

    def __init__(self, html: str):
        """Initialize the scrape page data."""
        self.html = html
        self.request_time_ms: float = 0
        self.status = ScrapeStatus.UNKNOWN


class ScrapeResult():
    """Class to keep the Download Result Data."""

    def __init__(self, url: str):
        """Initialize the Scrape Result."""
        self._scrape_pages: List[ScrapePage] = []
        self._idx = 0

        self.url = url

        # TODO - Status should be (_scrape_pages > 0) and (not error_msg)
        # TODO - Or some other logic
        self.status: ScrapeStatus = ScrapeStatus.UNKNOWN
        self.error_msg = ''

        self._raw_response = None


    @property
    def request_time_ms(self) -> float:
        """Property to calculate the combined request time."""
        req_time = 0.0
        for page in self:
            req_time += page.request_time_ms
        return req_time

    def add_scrape_page(self, html: str, *,
                        scrape_time: float = 0,
                        status: ScrapeStatus) -> None:
        """Add a scraped page."""
        page = ScrapePage(html)
        page.request_time_ms = scrape_time
        page.status = status
        self._scrape_pages.append(page)

    def __iter__(self) -> Iterator[ScrapePage]:
        self._idx = 0
        return self

    def __next__(self) -> ScrapePage:
        try:
            item = self._scrape_pages[self._idx]
        except IndexError:
            raise StopIteration()
        self._idx += 1
        return item

    def __len__(self) -> int:
        return len(self._scrape_pages)

    def __bool__(self) -> bool:
        return self.status == ScrapeStatus.SUCCESS


class Scraper():
    """Base Class for Scraper Functionality."""

    def __init__(self, config: ScrapeConfig):
        """Initialize the Scrape Class."""
        self.config: ScrapeConfig = config

    def scrape(self) -> ScrapeResult:
        """Scrape based on the set config."""
        raise NotImplementedError

    @classmethod
    def _validate_config(cls, config: ScrapeConfig) -> None:
        """Validate the Scrapers config."""
        if config is None:
            raise ValueError("Config must be provided")

    @property
    def config(self) -> ScrapeConfig:
        """Property to define the config parameter."""
        return self._config

    @config.setter
    def config(self, new_config: ScrapeConfig) -> None:
        # Check in setter because True for subclasses as well
        if new_config is None:
            raise ValueError("Config must be provided")

        self._validate_config(new_config)

        # pylint: disable=attribute-defined-outside-init
        self._config = new_config
        # pylint: enable=attribute-defined-outside-init


def generic_useragent():
    """Generate a generic user agent."""
    return fake_useragent.UserAgent().chrome
