from datetime import datetime
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')

def template_document(
    user_id,
    name,
    template_type,
    content,
    media=None,
    status="pending"
):
    """
    RCS Template Document
    Compatible with Jio RCS (Text, Rich Card, Carousel)
    """

    return {
        "user_id": user_id,
        "name": name.strip(),
        "template_type": template_type,   # text | rich | carousel
        "content": content,               # structured JSON
        "media": media,                   # image / video metadata
        "status": status,                 # pending | approved | rejected
        "rejection_reason": None,

        "created_at": datetime.now(IST),
        "updated_at": datetime.now(IST),
        "approved_at": None,
    }

