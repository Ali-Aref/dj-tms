import json
import time


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        t0 = time.time()
        req_body = None
        if request.body:
            try:
                req_body = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                req_body = request.body.decode("utf-8", errors="replace")
        response = self.get_response(request)
        ms = int((time.time() - t0) * 1000)
        res_body = None
        if response.content:
            try:
                res_body = json.loads(response.content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                res_body = response.content.decode("utf-8", errors="replace")
        res_log = "null" if response.status_code == 204 or not response.content else json.dumps(res_body)
        print(
            f"{request.method} {request.path} {response.status_code} {ms}ms\n"
            f"  req {json.dumps(req_body)}\n"
            f"  res {res_log}"
        )
        return response
