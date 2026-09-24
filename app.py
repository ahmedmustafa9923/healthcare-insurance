import os
from http.server import SimpleHTTPRequestHandler, HTTPServer

class HealthcareApp(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        output = "==================================================\n"
        output += "  HEALTHCARE & INSURANCE ENTERPRISE DATA CLUSTER   \n"
        output += "==================================================\n\n"
        for root, dirs, files in sorted(os.walk(".")):
            if ".git" in root or "Dockerfile" in files:
                continue
            level = root.replace('.', '').count(os.sep)
            indent = ' ' * 4 * (level)
            output += f"{indent}[+] {os.path.basename(root)}/\n"
            subindent = ' ' * 4 * (level + 1)
            for f in sorted(files):
                if f != "app.py" and f != "Dockerfile":
                    output += f"{subindent}└── [File] {f}\n"
        self.wfile.write(output.encode())

print("Enterprise App serving on port 8080...")
HTTPServer(('0.0.0.0', 8080), HealthcareApp).serve_forever()


