"""
Agilico Contact Importer - Lite
Selenium WebDriver Factory, Lock-Safe Anti-Throttling Configurations, and DOM Utilities.
"""

import time
from typing import Callable, List, Optional, Tuple

import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    ElementNotInteractableException,
    UnexpectedAlertPresentException,
)

from constants import (
    DISMISS_XPATHS,
    USER_XPATHS,
    PWD_XPATHS,
    SUBMIT_XPATHS,
    AUTH_ERROR_XPATHS,
    NAV_BACK_XPATHS,
    SEARCH_BOX_XPATHS,
    ADD_CONTACT_XPATHS,
    SAVE_BUTTON_XPATHS,
    MODAL_SAVE_BUTTON_XPATHS,
    ADD_NUMBER_BUTTON_XPATHS,
    FORM_INDICATOR_XPATHS,
)
from models import ImportStoppedException


class BrowserEngine:
    """Manages WebDriver lifecycle, anti-throttling options, and resilient DOM operations."""

    @staticmethod
    def create_driver(browser_choice: str, logger: Optional[Callable[[str, str], None]] = None) -> Tuple[webdriver.Remote, str]:
        """
        Creates and configures a WebDriver instance with Lock-Safe Anti-Throttling flags.
        Supports Microsoft Edge, Google Chrome, and Mozilla Firefox.
        """
        b_lower = browser_choice.lower()
        is_headless = "headless" in b_lower or "lock-safe" in b_lower

        def _log(msg: str, lvl: str = "INFO"):
            if logger:
                logger(msg, lvl)

        def try_edge():
            opts = EdgeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--remote-allow-origins=*")
            opts.add_argument("--ignore-certificate-errors")
            # Anti-throttling & Lock-Safe flags: prevents Windows Lock Screen (Win+L) occlusion throttling
            opts.add_argument("--disable-background-timer-throttling")
            opts.add_argument("--disable-backgrounding-occluded-windows")
            opts.add_argument("--disable-renderer-backgrounding")
            opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            if is_headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--disable-gpu")
            driver = webdriver.Edge(options=opts)
            name = "Microsoft Edge" + (" (Headless / Lock-Safe)" if is_headless else "")
            return driver, name

        def try_chrome():
            opts = ChromeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--remote-allow-origins=*")
            opts.add_argument("--ignore-certificate-errors")
            # Anti-throttling & Lock-Safe flags
            opts.add_argument("--disable-background-timer-throttling")
            opts.add_argument("--disable-backgrounding-occluded-windows")
            opts.add_argument("--disable-renderer-backgrounding")
            opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            if is_headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--disable-gpu")
            driver = webdriver.Chrome(options=opts)
            name = "Google Chrome" + (" (Headless / Lock-Safe)" if is_headless else "")
            return driver, name

        def try_firefox():
            opts = FirefoxOptions()
            opts.set_preference("dom.webdriver.enabled", False)
            opts.set_preference("useAutomationExtension", False)
            opts.set_preference("dom.disable_beforeunload", True)
            opts.set_preference("dom.min_background_timeout_value", 10)
            opts.set_preference("dom.timeout.enable_budget_timer_throttling", False)
            if is_headless:
                opts.add_argument("-headless")
                opts.add_argument("--window-size=1920,1080")
            driver = webdriver.Firefox(options=opts)
            name = "Mozilla Firefox" + (" (Headless / Lock-Safe)" if is_headless else "")
            return driver, name

        if "edge" in b_lower and "auto" not in b_lower:
            try:
                return try_edge()
            except Exception as e:
                _log(f"Microsoft Edge launch issue ({str(e).splitlines()[0]}). Trying fallback browsers...", "WARNING")
        elif "chrome" in b_lower and "auto" not in b_lower:
            try:
                return try_chrome()
            except Exception as e:
                _log(f"Google Chrome launch issue ({str(e).splitlines()[0]}). Trying fallback browsers...", "WARNING")
        elif "firefox" in b_lower and "auto" not in b_lower:
            try:
                return try_firefox()
            except Exception as e:
                _log(f"Mozilla Firefox launch issue ({str(e).splitlines()[0]}). Trying fallback browsers...", "WARNING")

        attempts = [
            ("Microsoft Edge", try_edge),
            ("Google Chrome", try_chrome),
            ("Mozilla Firefox", try_firefox),
        ]

        last_err = None
        for name, launcher in attempts:
            try:
                _log(f"Attempting to launch {name}...", "INFO")
                driver, b_name = launcher()
                return driver, b_name
            except Exception as ex:
                last_err = ex
                _log(f"{name} not available or failed to start: {str(ex).splitlines()[0]}", "MUTED")

        raise WebDriverException(f"Could not find or launch any supported browser (Edge, Chrome, Firefox). Last error: {last_err}")

    @staticmethod
    def dismiss_portal_overlays(driver):
        """Proactively dismisses cookie consent popups, service alerts, and stray backdrop masks."""
        if not driver:
            return
        for xp in DISMISS_XPATHS:
            try:
                elems = driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        driver.execute_script("arguments[0].click();", el)
                        break
            except Exception:
                pass

    @staticmethod
    def wait_for_page_ready(driver, timeout: float = 15.0):
        """Waits for the browser DOM and active network requests to finish loading."""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        BrowserEngine.dismiss_portal_overlays(driver)

    @staticmethod
    def safe_click(driver, element, retries: int = 3) -> bool:
        """Scrolls element into center and clicks with robust JavaScript fallback."""
        if not driver or not element:
            return False
        for attempt in range(retries):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
                time.sleep(0.08)
                element.click()
                return True
            except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    time.sleep(0.12)
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    time.sleep(0.12)
        return False

    @staticmethod
    def populate_input(driver, element, value: str):
        """Focuses, clears, and inputs text into an input element and triggers input/change/blur framework events."""
        if not driver or not element or value is None:
            return
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.04)
            element.click()
            element.clear()
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.BACKSPACE)
            time.sleep(0.02)
            element.send_keys(value)
            time.sleep(0.04)
        except Exception:
            pass

        try:
            driver.execute_script(
                "var el = arguments[0];"
                "if (window.$ && $(el).length) {"
                "    $(el).trigger('input').trigger('change').trigger('blur');"
                "} else {"
                "    el.dispatchEvent(new Event('input', { bubbles: true }));"
                "    el.dispatchEvent(new Event('change', { bubbles: true }));"
                "    el.dispatchEvent(new Event('blur', { bubbles: true }));"
                "}",
                element,
            )
            time.sleep(0.03)
        except Exception:
            pass

    @staticmethod
    def is_back_or_nav_element(el) -> bool:
        """Checks if an element is a Back, Cancel, or return-to-list navigation button."""
        try:
            text = (el.text or "").strip().lower()
            if any(b == text or text.startswith(b) for b in ["back", "cancel", "return", "close", "exit", "back to list"]):
                return True
            href = (el.get_attribute("href") or "").lower()
            if href:
                if (href.rstrip("/").endswith("/contacts") or "/account" in href or "changetenant" in href) and "number" not in href:
                    return True
            icons = el.find_elements(By.XPATH, ".//i | .//span")
            for ic in icons:
                cls = (ic.get_attribute("class") or "").lower()
                if any(c in cls for c in ["fa-arrow-left", "fa-chevron-left", "fa-backward", "fa-reply", "fa-undo", "fa-times"]):
                    return True
        except Exception:
            pass
        return False
