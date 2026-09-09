from django.core.cache import cache
from django.conf import settings
from Raynder.settings import TENDERTIGER_EMAIL, TENDERTIGER_PASSWORD
from crawlers.tendertiger.crawler.auth import TenderTigerAuth
from dotenv import load_dotenv
import os
load_dotenv()

class TenderTigerAuthManager:

    CACHE_KEY = "crawler:tendertiger:auth"

    # 4 hours for now
    CACHE_TIMEOUT = 60 * 60 * 4

    @classmethod
    def get_auth(cls):
        """
        Return an authenticated TenderTigerAuth object.
        If authentication exists in cache, restore it.
        Otherwise login and store the authentication state.
        """
        auth = TenderTigerAuth()

        # 1. Check cache
        cached_state = cache.get(cls.CACHE_KEY)

        if cached_state:

            print("TenderTiger authentication found in cache.")

            # 2. Restore authentication
            auth.restore_auth_state(cached_state)

            if auth.is_authenticated():
                print("Using cached TenderTiger authentication.")
                return auth

            print("Cached authentication is invalid.")
        # 3. Login if authentication is not available
        print("Logging in to TenderTiger...")

        auth.open_login_page()
        auth.login(
            TENDERTIGER_EMAIL,
            TENDERTIGER_PASSWORD,
        )

        # 4. Save authentication
        cls.save_auth(auth)
        return auth

    @classmethod
    def save_auth(cls, auth):
        """
        Save TenderTiger authentication state to Django cache.
        """

        state = auth.export_auth_state()

        cache.set(
            cls.CACHE_KEY,
            state,
            timeout=cls.CACHE_TIMEOUT,
        )

        print("TenderTiger authentication saved to cache.")

    @classmethod
    def clear_auth(cls):
        """
        Remove TenderTiger authentication from cache.
        """

        cache.delete(cls.CACHE_KEY)

        print("TenderTiger authentication removed from cache.")