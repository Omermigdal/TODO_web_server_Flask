import flask
import time
from flask import Flask, request, jsonify
from datetime import datetime
import logging
import json
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_pymongo import PyMongo

logs_directory = 'logs'
if os.path.isdir("logs") == False:
    os.makedirs(logs_directory)
app = Flask(__name__)
request_counter = 1


app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:docker@postgres:5432/todos'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MONGO_URI'] = 'mongodb://mongo:27017/todos'

db = SQLAlchemy(app)
mongo = PyMongo(app)


# Global variable to store the count of TODOs
count_TODOS = 0

# Function to update the count of TODOs
def update_TODO_count():
    global count_TODOS
    count_TODOS = TODO_Model.query.count()



class TODO_Model(db.Model):
    __tablename__ = 'todos'
    rawid = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.String(255), nullable=False)
    duedate = db.Column(db.DateTime, nullable=False)
    state = db.Column(db.String(50), nullable=False)

    def to_json(self):
        return {"id": self.rawid, "title": self.title, "content": self.content, "dueDate": self.duedate, "status": self.state}
    


    def __init__(self, rawid, title, content, duedate, state):
        self.rawid = rawid
        self.title = title
        self.content = content
        self.duedate = duedate
        self.state = state



'''FORMATTER'''
formatter = logging.Formatter(f"%(asctime)s.%(msecs)03d %(levelname)s: %(message)s | request #%(request_counter)s",
                              datefmt='%d-%m-%Y %H:%M:%S')

'''HANDLERS'''
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
consoleHandler.setFormatter(formatter)
req_fileHandler = logging.FileHandler(os.path.join(logs_directory, 'requests.log'))
req_fileHandler.setFormatter(formatter)
TOOO_fileHandler = logging.FileHandler(os.path.join(logs_directory, 'todos.log'))
TOOO_fileHandler.setFormatter(formatter)

'''LOGGERS'''
request_logger = logging.getLogger('request-logger')
request_logger.setLevel(logging.INFO)
request_logger.addHandler(consoleHandler)
request_logger.addHandler(req_fileHandler)

TODO_logger = logging.getLogger('todo-logger')
TODO_logger.setLevel(logging.INFO)
TODO_logger.addHandler(consoleHandler)
TODO_logger.addHandler(TOOO_fileHandler)

loggingLevels = {'0': "NONSET",
                 '10': "DEBUG",
                 '20': "INFO",
                 '30': "WARNING",
                 '40': "ERROR"
                 }


# Health endpoint
@app.route('/todo/health', methods=['GET'])
def health():
    start = time.time()
    global request_counter

    request_logger.info(f"Incoming request | #{request_counter} | resource: /todo/health | HTTP Verb GET",
                        extra={'request_counter': request_counter})
    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms",
                         extra={'request_counter': request_counter})
    request_counter += 1
    return "OK"


# Create new TODO endpoint
@app.route('/todo', methods=['POST'])
def create_TODO():
    start = time.time()
    is_valid_todo = True

    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /todo | HTTP Verb POST",
                        extra={'request_counter': request_counter})

    received_title = request.json["title"]
    received_content = request.json["content"]
    received_due_date = request.json["dueDate"]

    existing_TODO = TODO_Model.query.filter_by(title=received_title).first()

    if existing_TODO is not None:
        response = jsonify(
            {"errorMessage": "Error: TODO with the title [" + existing_TODO.title + "] already exists in the system"})
        response.status_code = 409
        TODO_logger.error("Error: TODO with the title [" + existing_TODO.title + "] already exists in the system",
                          extra={'request_counter': request_counter})
        return response

    # Checking if the due date received is in the past
    curr_time_ms = datetime.now().timestamp() * 1000  # current time  to milliseconds
    if received_due_date < curr_time_ms:
        response = jsonify({'errorMessage': "Error: Can\'t create new TODO that its due date is in the past"})
        response.status_code = 409
        TODO_logger.error("Error:  Can\'t create new TODO that its due date is in the past",
                          extra={'request_counter': request_counter})
        return response


    TODO_logger.info(f"Creating new TODO with Title [{received_title}]", extra={'request_counter': request_counter})
    TODO_logger.debug(
        f"Currently there are {count_TODOS} TODOs in the system. New TODO will be assigned with id {count_TODOS + 1}",
        extra={'request_counter': request_counter})

    latest_rawid = db.session.query(func.max(TODO_Model.rawid)).scalar()
    TODO_id = 1 if latest_rawid is None else latest_rawid + 1
    new_TODO = {
        "id": TODO_id,
        "title": received_title,
        "content": received_content,
        "status": "PENDING",
        "dueDate": received_due_date
    }

    TODO_to_table = TODO_Model(TODO_id, new_TODO['title'], new_TODO['content'], new_TODO['dueDate'], new_TODO['status'])
    db.session.add(TODO_to_table)
    db.session.commit()

    mongo.db.todos.insert_one({
        'rawid': TODO_id,
        'title': new_TODO['title'],
        'content': new_TODO['content'],
        'duedate': new_TODO['dueDate'],
        'state': new_TODO['status']
    })

    response = jsonify({"result": new_TODO["id"]})
    response.status_code = 200

    update_TODO_count()

    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms",extra={'request_counter': request_counter})
    request_counter += 1

    return response




@app.route('/todo/size', methods=['GET'])
def count_TODOs_by_status():
    start = time.time()
    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /todo/size | HTTP Verb GET", extra={'request_counter': request_counter})

    received_status = request.args.get("status")
    chosen_DB = request.args.get('persistenceMethod')

    if received_status not in ["ALL", "PENDING", "LATE", "DONE"]:
        response = jsonify({"errorMessage": "Invalid status"})
        response.status_code = 400
    elif received_status == "ALL":
        if chosen_DB == 'POSTGRES':
            count =  db.session.query(func.max(TODO_Model.rawid)).scalar()
            response = jsonify({"result":count})
        else:
            count = mongo.db.todos.count_documents({})
            response = jsonify({"result": count})
        response.status_code = 200
    else:
        if chosen_DB == 'POSTGRES':
            count = TODO_Model.query.filter(TODO_Model.state == received_status).count()
        else:
            count = mongo.db.todos.count_documents({'state': received_status})
        response = jsonify({"result": count})
        response.status_code = 200

    end = time.time()
    total_time_ms = ((end - start) * 1000)
    TODO_logger.info(f"Total TODOs count for state {received_status} is {count}",
                     extra={'request_counter': request_counter})
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms",
                         extra={'request_counter': request_counter})
    request_counter += 1

    return response




@app.route('/todo/content', methods=['GET'])
def get_TODOs_by_status():
    start = time.time()
    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /todo/content | HTTP Verb GET",
                        extra={'request_counter': request_counter})

    received_status = request.args.get('status')
    received_sortBy = request.args.get('sortBy')
    chosen_DB = request.args.get('persistenceMethod')

    res_TODO_list = []

    if received_status not in ["ALL", "PENDING", "LATE", "DONE"] or received_sortBy not in ["ID", "DUE_DATE", "TITLE",None]:
        response = jsonify()
        response.status_code = 400

    if received_sortBy == None:
        received_sortBy = "id"
    elif received_sortBy == "DUE_DATE":
        received_sortBy = "dueDate"
    else:
        received_sortBy = received_sortBy.lower()

    TODO_logger.info(f"Extracting todos content. Filter: {received_status} | Sorting by: {received_sortBy.upper()}",
                     extra={'request_counter': request_counter})

    ''' returning all TODOs'''
    if chosen_DB == 'POSTGRES':
        if received_status == "ALL":
            res_TODO_list = TODO_Model.query.order_by(getattr(TODO_Model, received_sortBy)).all()
        else:
            res_TODO_list = TODO_Model.query.filter(TODO_Model.state == received_status).order_by(getattr(TODO_Model, received_sortBy)).all()
        
        todo_dicts  = [todo.to_json() for todo in res_TODO_list]
        # Sort the list based on the specified attribute
        sorted_list = sorted(todo_dicts, key=lambda x: x[received_sortBy])

        # Return the response
        response = flask.Response(json.dumps({"result": sorted_list}), status=200, content_type='application/json')


    else:
        if received_status == "ALL":
            res_TODO_list = list(mongo.db.todos.find())
            res = [
                {"id": todo['rawid'],
                 "title": todo['title'],
                 "content": todo['content'],
                 "status": todo['state'],
                 "dueDate": todo['duedate']
                 } for todo in res_TODO_list]

            res.sort(key=lambda x: x[received_sortBy])

        else:
            res_TODO_list = list(mongo.db.todos.find({'state': received_status}))
            res = [
                {"id": todo['rawid'],
                 "title": todo['title'],
                 "content": todo['content'],
                 "status":todo['state'],
                 "dueDate": todo['duedate']
                 } for todo in res_TODO_list]
            res.sort(key=lambda x: x[received_sortBy])


        response = flask.Response(json.dumps({"result": res}), status=200, content_type='application/json')

    update_TODO_count()
    TODO_logger.debug(
        f"There are a total of {count_TODOS} todos in the system. The result holds {len(res_TODO_list)} todos",
        extra={'request_counter': request_counter})
    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms",
                         extra={'request_counter': request_counter})
    request_counter += 1

    return response




@app.route('/todo', methods=['PUT'])
def update_TODO():
    start = time.time()
    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /todo | HTTP Verb PUT",extra={'request_counter': request_counter})

    TODO_to_upadte_id = int(request.args.get('id'))
    change_status_to = request.args.get('status')
    if change_status_to not in ["ALL", "PENDING", "LATE", "DONE"]:
        response = jsonify({"errorMessage": "Error: Invalid status"})
        response.status_code = 400
        request_counter += 1
        return response
    found = False

    TODO_logger.info(f"Update TODO id [{TODO_to_upadte_id}] state to {change_status_to}",extra={'request_counter': request_counter})

    TODO_to_update_Postgres = db.session.query(TODO_Model).filter(TODO_Model.rawid == TODO_to_upadte_id).first()
    TODO_to_update_MONGO = mongo.db.todos.find({'id': TODO_to_upadte_id})

    if TODO_to_update_Postgres is not None:
        old_status = TODO_to_update_Postgres.state
        TODO_to_update_Postgres.state = change_status_to
        mongo.db.todos.update_one({'rawid': TODO_to_upadte_id}, {'$set': {'state': change_status_to}})
        db.session.commit()
        response = jsonify({"result": old_status})
        response.status_code = 200
        TODO_logger.debug(f"Todo id [{TODO_to_upadte_id}] state change: {old_status} --> {change_status_to}",extra={'request_counter': request_counter})

    else:
        response = jsonify({"errorMessage": "Error: no such TODO with id " + str(TODO_to_upadte_id)})
        response.status_code = 404
        TODO_logger.error("Error: no such TODO with id %d", TODO_to_upadte_id,extra={'request_counter': request_counter})

    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms", extra={'request_counter': request_counter})
    request_counter += 1

    return response


@app.route('/todo', methods=['DELETE'])
def delete_TODO():
    start = time.time()
    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /todo | HTTP Verb DELETE", extra={'request_counter': request_counter})

    TODO_to_delete_id = int(request.args.get('id'))

    TODO_to_delete_Postgres = db.session.query(TODO_Model).filter(TODO_Model.rawid == TODO_to_delete_id).first()
    TODO_to_delete_MONGO = mongo.db.todos.find({'rawid': TODO_to_delete_id})

    if TODO_to_delete_Postgres is not None and TODO_to_delete_MONGO is not None:
        db.session.delete(TODO_to_delete_Postgres)
        db.session.commit()
        mongo.db.todos.delete_one({'rawid': TODO_to_delete_id})
        TODO_logger.info(f"Removing todo id {TODO_to_delete_id}", extra={'request_counter': request_counter})
        res = db.session.query(TODO_Model).count()
        TODO_logger.debug(f"After removing todo id [{TODO_to_delete_id}] there are {res} TODOs in the system",extra={'request_counter': request_counter})
        response = jsonify({"result": res})
        response.status_code = 200
    else:
        response = jsonify({"errorMessage": "Error: no such TODO with id " + str(TODO_to_delete_id)})
        response.status_code = 404
        TODO_logger.error("Error: no such TODO with id %d", TODO_to_delete_id,extra={'request_counter': request_counter})
    
    update_TODO_count()
    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms", extra={'request_counter': request_counter})
    request_counter += 1

    return response


@app.route('/logs/level', methods=['GET'])
def get_logger_level():
    start = time.time()
    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /logs/level | HTTP Verb GET",
                        extra={'request_counter': request_counter})

    received_logger = request.args.get('logger-name')
    if received_logger not in ['request-logger', 'todo-logger']:
        response = "Failure: No such logger in the system...."
    else:
        response = "Success:%s", loggingLevels[str(received_logger.level)]
    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms",
                         extra={'request_counter': request_counter})
    request_counter += 1

    return response


@app.route('/logs/level', methods=['PUT'])
def set_logger_level():
    start = time.time()
    global request_counter
    request_logger.info(f"Incoming request | #{request_counter} | resource: /logs/level | HTTP Verb PUT",
                        extra={'request_counter': request_counter})

    received_logger = request.args.get('logger-name')
    received_level = request.args.get('logger-level')

    if received_logger not in ['request-logger', 'todo-logger']:
        response = "Failure: No such logger in the system...."
    elif received_level not in ['ERROR', 'INFO', 'DEBUG']:
        response = "Failure: No such level in the logging method...."
    else:
        if received_logger == 'request-logger':
            logger = request_logger
        else:
            logger = TODO_logger

        if received_level == 'ERROR':
            logger.setLevel(logging.ERROR)
        elif received_level == 'INFO':
            logger.setLevel(logging.INFO)
        elif received_level == 'DEBUG':
            logger.setLevel(logging.DEBUG)

        response = "Success: Updated logger level to " + received_level
    end = time.time()
    total_time_ms = ((end - start) * 1000)
    request_logger.debug(f"request #{request_counter} duration: {total_time_ms}ms",
                         extra={'request_counter': request_counter})
    request_counter += 1

    return response


app.run("0.0.0.0", 9285)
