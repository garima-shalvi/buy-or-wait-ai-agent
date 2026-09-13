from data_loader import load_data

def build_context(request_id, data):
    requests = data["requests"]
    profiles = data["profiles"]
    events = data["events"]
    payment_options = data["payment_options"]
    messages = data["messages"]
    images = data["images"]

    request = requests[requests["request_id"] == request_id].iloc[0]
    user_id = request["user_id"]

    profile = profiles[profiles["user_id"] == user_id].iloc[0]

    user_events = events[events["user_id"] == user_id].copy()
    event_ids = set(user_events["event_id"])

    user_messages = messages[messages["user_id"] == user_id].copy()

    request_messages = user_messages[
        user_messages["request_id"] == request_id
    ].copy()

    event_messages = user_messages[
        user_messages["related_event_id"].isin(event_ids)
    ].copy()

    user_images = images[images["user_id"] == user_id].copy()

    request_images = user_images[
        user_images["request_id"] == request_id
    ].copy()

    event_images = user_images[
        user_images["related_event_id"].isin(event_ids)
    ].copy()

    request_options = payment_options[
        payment_options["request_id"] == request_id
    ].copy()

    return {
        "request": request,
        "profile": profile,
        "events": user_events,
        "messages": user_messages,
        "request_messages": request_messages,
        "event_messages": event_messages,
        "images": user_images,
        "request_images": request_images,
        "event_images": event_images,
        "payment_options": request_options
    }

if __name__ == "__main__":
    data = load_data()
    context = build_context("request_26", data)

    for key, value in context.items():
        if hasattr(value, "shape"):
            print(f"{key}: {value.shape}")
        else:
            print(f"{key}: 1 row")