from your_app_name import create_app, db, socketio

app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=True)
    # app.run(debug=True)
