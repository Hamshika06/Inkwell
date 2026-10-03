"""Local Stage 1 demo: python -m demo.server --run runs/svm-opp115-seed42."""
import argparse,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from inkwell.predict import Predictor
from inkwell.stage1 import analyze

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!="/": self.send_error(404); return
        self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers()
        self.wfile.write(Path(__file__).with_name("index.html").read_bytes())
    def do_POST(self):
        if self.path!="/analyze": self.send_error(404);return
        size=int(self.headers.get("Content-Length",0))
        if size>1000000: self.send_error(413);return
        try:
            text=json.loads(self.rfile.read(size))["text"]
            if not isinstance(text,str): raise ValueError("text must be a string")
            result=analyze(text,self.server.predictor)
        except (KeyError,ValueError) as error:
            self.send_error(400,str(error));return
        self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
        self.wfile.write(json.dumps(result).encode())

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--run",required=True);ap.add_argument("--port",type=int,default=8765);args=ap.parse_args()
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler);server.predictor=Predictor(args.run)
    print(f"Open http://127.0.0.1:{args.port}",flush=True);server.serve_forever()
if __name__=="__main__": main()
