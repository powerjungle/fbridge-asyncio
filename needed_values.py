class NeededVars:
    threads = dict()
    users = dict()
    stream_api_url = None
    messages_api_url = None
    message_api_url = None
    reverse_threads = dict()  # Reverse lookup
    fb_listener_global = None
    timeout_listen = 0
    api_client = None
    run_infinite_timer = True
    timed_out = False
    listen_api_mode = None
