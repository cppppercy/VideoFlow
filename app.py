from videoflow.ui import create_app


if __name__ == "__main__":
    create_app().launch(server_name="127.0.0.1", share=False)
