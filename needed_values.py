class NeededVars:
    threads = dict()
    users = dict()
    stream_api_url = None
    reverse_threads = dict()  # Reverse lookup
    fb_listener_global = None
    timeout_listen = 0
