import json
import requests
from bs4 import BeautifulSoup


class TenderTigerAuth:
    """
    Handles authentication and maintains a logged-in session
    with the TenderTiger website.
    """

    BASE_URL = "https://www.tendertiger.co.in"

    def __init__(self):
        """
        Creates a requests session and initializes authentication data.
        """

        # Create session so cookies are preserved
        self.session = requests.Session()

        # Default headers
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE_URL}/",
            "Upgrade-Insecure-Requests": "1",
        })

        # Authentication state
        self.user = None
        self.customer_id = None
        self.user_detail_id = None
        self.token = None
        self.refresh_token = None
        self.tt_auth_token = None
        self.subscription = None

        self.authenticated = False

    def get_session(self):
        """
        Returns the current requests session.
        """
        return self.session

    def print_cookies(self):
        """
        Prints all cookies currently stored in the session.
        """
        print(self.session.cookies.get_dict())

    def open_login_page(self):
        """
        Opens the login page and stores the session cookies.
        """

        url = f"{self.BASE_URL}/User/Account?login"

        response = self.session.get(url)

        print("=" * 50)
        print("Status Code :", response.status_code)
        print("URL         :", response.url)
        print("=" * 50)

        return response

    def get_login_token(self):
        """
        Downloads the login form and extracts the CSRF token.
        """

        url = f"{self.BASE_URL}/User/Login"

        response = self.session.get(
            url,
            headers={
                "X-Requested-With": "XMLHttpRequest"
            }
        )

        print("Login Partial Status:", response.status_code)

        soup = BeautifulSoup(response.text, "html.parser")

        token = soup.find(
            "input",
            {
                "name": "__RequestVerificationToken"
            }
        )

        if token is None:
            raise Exception("CSRF token not found!")

        csrf = token["value"]

        print("CSRF Token Found!")

        return csrf

    def login(self, email, password):
        """
        Login to TenderTiger.
        """

        token = self.get_login_token()

        payload = {
            "Email": email,
            "Password": password,
            "__RequestVerificationToken": token,
            "ReturnUrl": "",
            "redirect_uri": "",
            "code_challenge": "",
            "state": "",
        }

        response = self.session.post(
            f"{self.BASE_URL}/User/Login",
            data=payload,
            headers={
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/User/Account?login",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        response.raise_for_status()

        data = response.json()

        # TenderTiger sometimes returns JSON inside a JSON string
        if isinstance(data, str):
            data = json.loads(data)

        if data.get("SuccessCode") != 3:
            raise Exception(
                f"TenderTiger login failed: "
                f"{data.get('SuccessMessage', 'Unknown error')}"
            )

        # Store authentication information
        self.user = data
        self.customer_id = data["CustomerId"]
        self.user_detail_id = data["UserDetailId"]
        self.token = data["Token"]
        self.refresh_token = data["RefreshToken"]
        self.tt_auth_token = data["tt_auth_token"]
        self.subscription = data["customerList"][0]

        self.authenticated = True

        print("✅ Login Successful")
        print("Customer ID :", self.customer_id)
        print("Subscription :", self.subscription["SubNo"])

        return data

    def is_authenticated(self):
        """
        Checks whether this object currently contains
        TenderTiger authentication information.
        """

        return (
            self.authenticated
            and self.tt_auth_token is not None
            and self.subscription is not None
        )

    def export_auth_state(self):
        """
        Converts authentication state into a dictionary
        that can be stored in Django cache / Redis.
        """

        return {
            "customer_id": self.customer_id,
            "user_detail_id": self.user_detail_id,
            "token": self.token,
            "refresh_token": self.refresh_token,
            "tt_auth_token": self.tt_auth_token,
            "subscription": self.subscription,
            "cookies": self.session.cookies.get_dict(),
            "authenticated": self.authenticated,
        }

    def restore_auth_state(self, state):
        """
        Restores authentication information from
        Django cache / Redis.
        """

        if not state:
            return False

        self.customer_id = state.get("customer_id")
        self.user_detail_id = state.get("user_detail_id")
        self.token = state.get("token")
        self.refresh_token = state.get("refresh_token")
        self.tt_auth_token = state.get("tt_auth_token")
        self.subscription = state.get("subscription")
        self.authenticated = state.get("authenticated", False)

        # Restore cookies into the new requests.Session
        cookies = state.get("cookies", {})

        for name, value in cookies.items():
            self.session.cookies.set(
                name,
                value,
                domain="www.tendertiger.co.in"
            )

        return True