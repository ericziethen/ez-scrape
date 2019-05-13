#!/usr/bin/env python3

"""Provide Website downloading functionality."""

import datetime
import http
import ipaddress
import logging
import os
import requests
import requests_html
import selenium
import sys
import urllib.parse

from selenium import webdriver
from typing import Iterator, Optional

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

CHROME_WEBDRIVER_ENV_VAR = 'CHROME_WEBDRIVER_PATH'

DEFAULT_REQUEST_TIMEOUT = 5.0
DEFAULT_NEXT_PAGE_TIMEOUT = 3
DEFAULT_JAVASCRIPT_WAIT = 3.0

SPECIAL_LOCAL_ADDRESSES = [
    'localhost',
    '0.0',
    '127.1'
]
class ScrapeError(Exception):
    """Generic Page Scrape Error."""


class ScrapeConfigError(ScrapeError):
    """Error with the Scrape Config."""

class SeleniumSetupError(Exception):
    """Exception is Selenium is not Setup Correctly."""

class SeleniumChromeSession():
    """Context Manager for a Selenium Chrome Session."""


class ScrapeConfig():
    """Class to hold scrape config data needed for downloading the html."""

    def __init__(self, url: str):
        """Initialize a default scrape config with the given url."""
        self.url = url
        self.request_timeout = DEFAULT_REQUEST_TIMEOUT
        self.proxy_server = None
        self.javascript = False
        self.javascript_wait = DEFAULT_JAVASCRIPT_WAIT
        self.useragent = None
        self.attempt_multi_page = False  # TODO - Verify in the end if we even need this field or we can always do it without
        self.next_page_elem_xpath = None
        self.max_pages = sys.maxsize
        self.next_page_timeout = DEFAULT_NEXT_PAGE_TIMEOUT

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, new_url: str):
        if (not new_url) or (not isinstance(new_url, str)):
            raise ScrapeConfigError('Url cannot be blank')
        self._url = new_url


class ScrapePage():
    """Class to represent a single scraped page."""

    def __init__(self, html: str):
        """Initialize the scrape page data."""
        self.html = html
        self.request_time_ms: Optional[float] = None

class ScrapeResult():
    """Class to keep the Download Result Data."""
    
    def __init__(self, url: str):
        """Initialize the Scrape Result."""
        self._scrape_pages = []
        self._idx = 0

        self.url = url
        self.success = False
        self.error_msg = None

    @property
    def request_time_ms(self):
        req_time = 0
        for page in self:
            req_time += page.request_time_ms
        return req_time

    def add_scrape_page(self, html: str, *,
                        scrape_time: Optional[float] = None):
        """Add a scraped page."""
        page = ScrapePage(html)
        page.request_time_ms = scrape_time
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
        return self._scrape_pages is None


def _validate_config_for_requests(config: ScrapeConfig):
    """Check if Requests can handle this config."""
    if config.javascript:
        raise ScrapeConfigError("No Support for Javascript")

    if (config.attempt_multi_page or
            (config.next_page_elem_xpath is not None)):
        raise ScrapeConfigError("No Support for Multipages, check fields")


def _scrape_url_requests(config: ScrapeConfig) -> ScrapeResult:
    """Scrape using Requests."""
    _validate_config_for_requests(config)

    result = ScrapeResult(config.url)
    time = datetime.datetime.now()
    try:
        resp = requests.request('get', config.url,
                                timeout=config.request_timeout)
    except requests.RequestException as error:
        result.error_msg = F'EXCEPTION: {type(error).__name__} - {error}'
    else:
        if resp.status_code == 200:
            result.success = True
            timediff = datetime.datetime.now() - time
            scrape_time = (timediff.total_seconds() * 1000 +
                           timediff.microseconds / 1000)
            result.add_scrape_page(resp.text, scrape_time=scrape_time)
        else:
            result.error_msg = (F'HTTP Error: {resp.status_code} - '
                                F'{http.HTTPStatus(resp.status_code).phrase}')

    return result


def _validate_config_for_requests_html(config: ScrapeConfig):
    """Check if Requests can handle this config."""
    if config.next_page_elem_xpath is not None:
        raise ScrapeConfigError("No Suport for Next pages via Xpath")


def _scrape_url_requests_html(config: ScrapeConfig) -> ScrapeResult:
    """Scrape using Requests-HTML."""
    _validate_config_for_requests_html(config)

    result = ScrapeResult(config.url)
    session = requests_html.HTMLSession()

    next_url = config.url
    count = 0
    while next_url is not None:
        logger.debug(F'Processing Url: "{next_url}"')
        count += 1

        # TODO - What if we have multiple pages?, do we need the request time for each?
        # Fire the Request
        time = datetime.datetime.now()
        try:
            resp = session.get(next_url, timeout=config.request_timeout)
        except requests.RequestException as error:
            result.error_msg = F'EXCEPTION: {type(error).__name__} - {error}'
        else:
            if config.javascript:
                resp.html.render(sleep=config.javascript_wait)
            if resp.status_code == 200:
                # TODO - What if we have multiple pages?, should we set the status separetely?
                # TODO We probably want to have the request time for each request and calculate the time as everage for each as a property
                result.success = True
                timediff = datetime.datetime.now() - time
                scrape_time = (timediff.total_seconds() * 1000 +
                               timediff.microseconds / 1000)
                result.add_scrape_page(resp.html.html, scrape_time=scrape_time)
            else:
                result.error_msg = (F'HTTP Error: {resp.status_code} - '
                                    F'{http.HTTPStatus(resp.status_code).phrase}')

        if count > config.max_pages:
            logger.debug(F'Paging limit of {config.max_pages} reached, '
                         'stop scraping')
            break

        if not config.attempt_multi_page:
            logger.debug((F'Multipage is not set, skip after first page'))
            break

        next_url = resp.html.next()

    return result


def _scrape_url_selenium_chrome(config: ScrapeConfig,
                                open_browser=None) -> ScrapeResult:
    """Scrape using Selenium with Chrome."""
    # TODO - Support Chrome Portable Overwrite
        # String chromePath = "M:/my/googlechromeporatble.exe path"; 
        #   options.setBinary(chromepath);
        #   System.setProperty("webdriver.chrome.driver",chromedriverpath);
    #chrome_exec_var=

    chrome_web_driver_path = os.environ.get(CHROME_WEBDRIVER_ENV_VAR)
    if chrome_web_driver_path is None:
        raise SeleniumSetupError((F'Webdriver not found, set path as env '
                                  F'Variable: "{CHROME_WEBDRIVER_ENV_VAR}"'))

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')

    result = ScrapeResult(config.url)

    with webdriver.Chrome(
            chrome_options=chrome_options,
            executable_path=chrome_web_driver_path) as browser:
        
        time = datetime.datetime.now()
        resp = browser.get(config.url)
        timediff = datetime.datetime.now() - time
        scrape_time = (timediff.total_seconds() * 1000 +
                       timediff.microseconds / 1000)

        result.success = True
        result.add_scrape_page(browser.page_source, scrape_time=scrape_time)

        '''
        # TODO - This needs Improvement to Not Do request multiple times
        if config.next_page_elem_xpath
        config.next_page_elem_xpath
        config.max_pages


        TODO !!! FIX ME 


        element = WebDriverWait(browser, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//li[@id='proxylisttable_next' and @class='fg-button ui-button ui-state-default next']/a")))
        print('  - Wait Finished')
        print('  - Element Enabled:', element.is_enabled())
        completeName = os.path.join('.', F'REQUESTS-SELENIUM_{x}.html')
        file_object = codecs.open(completeName, "w", "utf-8")
        html = browser.page_source
        file_object.write(html)
        print('  - HTML Written to', completeName)

        time.sleep(5)
        element.click();
        '''











    return result


def scrape_url(config: ScrapeConfig) -> ScrapeResult:
    """Generic function to handle all scraping requests."""
    raise NotImplementedError

def is_local_address(url: str) -> bool:
    """Simple check whether the given url is a local address."""
    # Parse the URL
    result = urllib.parse.urlparse(url)
    addr = result.netloc
    if not addr:
        addr = result.path
    addr = addr.split(':')[0].lower()

    # Check if it is a special local address
    if addr in SPECIAL_LOCAL_ADDRESSES:
        return True

    # Check the Ip Range
    is_private = False
    try:
        is_private = ipaddress.ip_address(addr).is_private
    except ValueError:
        is_private = False
    return is_private


def check_url(url: str, *, local_only: bool) -> bool:
    """Check if the Local url is reachable."""
    if local_only and (not is_local_address(url)):
        raise ValueError('Url is not a local address')

    config = ScrapeConfig(url)
    result = _scrape_url_requests(config)
    return result.success
























































##############################################################
#
###### OLD IMPLEMENTATION - REFACTOR
#
##############################################################





'''
class ScrapeError(Exception):
    """Generic Page Scrape Error."""


class ScrapeConfig():
    """Class to hold scrape config data needed for downloading the html."""

    def __init__(self, url) -> None:
        self.url
        self.proxy_server = ''
        self.javascript = False
        self.next_page_xpath = ''
        self.useragent = ''
        self.multipages = False
        self.max_pages = sys.maxsize
        self.next_page_timeout = 1
        # TODO - Define more fields whatever might be needed for scraping


class ScrapeResult():
    """Class to keep the Download Result Data."""

    def __init__(self, response):
        """Initialize the Scrape Result."""
        self._response = response               # Selenium Response is different, either subclass or none)
        self.html_pages = []
        self.status_code = response.status_code #(Can't get it from Selenium)
        self.next_page = None

    @property
    def result_good(self) -> bool:
        """Check if the result is ok,"""
        return self.status_code == 200

'''

'''
import requests
from selenium import webdriver

def test_scrape_selenium_chrome(url):
    with webdriver.Chrome(executable_path=R'D:\temp\chromedriver_win32\chromedriver.exe') as browser:
        r = browser.get(url)
        result = ScrapeResult(r)
        result.html_pages.append(browser.page_source)
        return result

def test_scrape_selenium_chrome_headless(url):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')


    with webdriver.Chrome(chrome_options=chrome_options, executable_path=R'D:\temp\chromedriver_win32\chromedriver.exe') as browser:
        r = browser.get(url)
        result = ScrapeResult(r)
        result.html_pages.append(browser.page_source)
        return result

def test_scrape_requests(url):
    r = requests.request('get', url)
    result = ScrapeResult(r)
    result.html_pages.append(r.text)
    return result

def test_scrape_html_requests(url):
    session = requests_html.HTMLSession()
    r = session.get(url)
    result = ScrapeResult(r)
    result.html_pages.append(r.html.html)
    return result
'''
'''
reuse_browser = webdriver.Chrome(executable_path=R'D:\temp\chromedriver_win32\chromedriver.exe')
chrome_options2 = webdriver.ChromeOptions()
chrome_options2.add_argument("--headless")
reuse_browser_headless = webdriver.Chrome(chrome_options=chrome_options2, executable_path=R'D:\temp\chromedriver_win32\chromedriver.exe')
'''
'''
def test_scrape_selenium_chrome_reuse(url):
    r = reuse_browser.get(R'chrome://version/')
    r = reuse_browser.get(url)
    result = ScrapeResult(r)
    result.html_pages.append(reuse_browser.page_source)
    return result

def test_scrape_selenium_chrome_headless_reuse(url):
    r = reuse_browser.get(R'chrome://version/')
    r = reuse_browser_headless.get(url)
    result = ScrapeResult(r)
    result.html_pages.append(reuse_browser_headless.page_source)
    return result




def test_scrape_selenium_chrome_headless_reuse_pass(url, browser):
    r = browser.get(R'chrome://version/')
    r = browser.get(url)
    result = ScrapeResult(r)
    result.html_pages.append(browser.page_source)
    return result
'''



'''
!!! ### SOME PROBLEMS
!!! 1.) If I cannot find a way to not download CHromium automatically, maybe easier
!!! to use headless chromium and then we don't need html-requests but onlye requests
!!! but it might be ok for us to do as well, esecially when using Internally and in an
!!! automated way it should only download once
!!! 2.) It does not do javascript pagination, so if that is essential use selenium for those
!!! 3.) Selenium uses browser "always?", for HTML pages we might just want to use requests-html
!!! 4.) Need to check Timinig, Selenium vs Requests vs HTML-Requests
!!! 5.) The Project should probably be called ezscraper to account for the actual purpose
'''
'''
def scrape_url(url: str, *, proxy_url: Optional[str] = None, wait: float = 0,
               load_javascript: bool = False) -> ScrapeResult:
    """Download the given url with the given proxy if specified."""

    session = requests_html.HTMLSession()
    response = session.get(url)
    if load_javascript:
        response.html.render(wait=wait)

    
    result = ScrapeResult(response)
    print('INITIAL NEXT PAGE:::', response.html.next())
    for html in response.html:
        if load_javascript:
            html.render(wait=wait)
        result.html_pages.append(html.html)
        print(F'ERIC:::"{html.html}"')
        print('NEXT PAGE:::', html.next())

    return result

'''