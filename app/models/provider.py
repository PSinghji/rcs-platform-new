def provider_document(
    name,
    provider_code,
    default_api_key=None,
    default_agent_id=None,
    active=True
):
    return {
        "name": name,                 # Jio, Airtel
        "provider_code": provider_code,  # jio, airtel
        "default_api_key": default_api_key,
        "default_agent_id": default_agent_id,
        "active": active
    }
