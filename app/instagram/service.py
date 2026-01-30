class InstagramAPIClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def send_dm(self, user_id: str, message: str):
        # existing logic here
        pass

    def process_comment(self, payload: dict):
        # existing logic here
        pass

