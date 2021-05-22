class NeededVars:
    threads = dict()
    users = dict()
    stream_api_url = None
    # Reverse lookup
    reverse_threads = dict()
    fb_listener_global = None
    timeout_listen = 0