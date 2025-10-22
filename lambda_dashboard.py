import serverless_wsgi
from app import app

def lambda_handler(event, context):
    """Lambda handler using serverless-wsgi"""
    return serverless_wsgi.handle_request(app, event, context)


# from asgiref.wsgi import WsgiToAsgi
# from mangum import Mangum
# from app import app

# # Convert Flask WSGI app to ASGI
# asgi_app = WsgiToAsgi(app)

# # Mangum adapter for AWS Lambda
# handler = Mangum(asgi_app, lifespan="off")

# def lambda_handler(event, context):
#     """Lambda handler that uses Mangum to convert Lambda events to Flask"""
#     return handler(event, context)