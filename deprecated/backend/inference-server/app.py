from sources.all_services import load_services
from flask import Flask, request
from waitress import serve
import os
import inspect
from flask import Response, stream_with_context
import json

def main():

    # Service loading
    print("Starting Based Inference Server...")
    services = load_services()
    for service in services:
        service.preload()
    print("Loaded services:")
    service_map = {}
    for service in services:
        print(" - " + service.name)
        service_map[service.name] = service

    # Service cache
    loaded_service = None
    def load_service(service_name):
        nonlocal loaded_service
        target_service = service_map[service_name]
        if loaded_service != service_name:
            if loaded_service is not None:
                old_service = service_map[loaded_service]
                old_service.unload()
            new_service = service_map[service_name]
            target_service.load()
            loaded_service = service_name
        return target_service
    
    # API server
    print("Starting API server...")
    app = Flask(__name__)
    @app.route('/')
    def index():
        return "Based Inference Server"
    @app.route('/service/<service_name>', methods=['POST'])
    def execute_service(service_name):
        if service_name not in service_map:
            return "Service not found", 404
        service = load_service(service_name)
        result = service.execute(request.json)
        if inspect.isgenerator(result):
            return Response(stream_with_context(json.dumps(item) + "\n" for item in result), mimetype='text/event-stream')
        else:
            return result

    # Run server
    if "PRODUCTION" in os.environ:
        serve(app, host='0.0.0.0', port=5000)
    else:
        app.run()


if __name__ == '__main__':
    main()