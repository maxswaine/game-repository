import os

import resend


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": to_email,
        "subject": "Reset your What's That Game password",
        "html": (
            f"<p>You requested a password reset for your What's That Game account.</p>"
            f"<p><a href=\"{reset_url}\">Click here to reset your password</a></p>"
            f"<p>This link expires in 15 minutes. If you didn't request this, you can safely ignore this email.</p>"
        ),
    })
