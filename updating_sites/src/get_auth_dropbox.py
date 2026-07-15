from services.dropbox_ import get_dropbox

if __name__ == "__main__":
    dropbox_service = get_dropbox()
    dropbox_service.authorize()
