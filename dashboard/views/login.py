import streamlit as st

from dashboard.api_client import APIConnectionError, APIError, HelpdeskAPIClient, SessionExpiredError


def render_login(client: HelpdeskAPIClient) -> None:
    """Render the Login / Register screen with tabs."""
    if "session_expired_message" in st.session_state:
        st.warning(st.session_state.pop("session_expired_message"))

    st.markdown("<h2 style='text-align: center;'>🎫 HelpDesk Portal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sign in or create a new account to continue</p>", unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔐 Login", "📝 Register"])

    with tab_login:
        st.subheader("Login to your account")
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@example.com").strip()
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In", use_container_width=True)

            if submit:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    try:
                        login_res = client.login(email=email, password=password)
                        user_info = client.get_me()

                        # Store only in memory in st.session_state (never on disk or URL)
                        st.session_state.token = login_res["access_token"]
                        st.session_state.user = user_info
                        st.session_state.current_page = "Tickets"
                        st.session_state.page = 1
                        st.success("Login successful!")
                        st.rerun()
                    except SessionExpiredError:
                        st.error("Invalid email or password.")
                    except APIConnectionError as e:
                        st.error(e.message)
                    except APIError as e:
                        st.error(e.message)

    with tab_register:
        st.subheader("Create a new Requester account")
        with st.form("register_form"):
            reg_full_name = st.text_input("Full Name", placeholder="Jane Doe").strip()
            reg_email = st.text_input("Email", placeholder="jane@example.com").strip()
            reg_password = st.text_input("Password (min 8 characters, max 72 bytes)", type="password")
            reg_submit = st.form_submit_button("Create Account", use_container_width=True)

            if reg_submit:
                if not reg_full_name or not reg_email or not reg_password:
                    st.error("All fields are required.")
                else:
                    try:
                        client.register(
                            email=reg_email,
                            full_name=reg_full_name,
                            password=reg_password,
                        )
                        st.success("Account created successfully! You can now log in using the Login tab.")
                    except APIConnectionError as e:
                        st.error(e.message)
                    except APIError as e:
                        st.error(e.message)
