# app.py
from flask import Flask, jsonify, request, current_app, Response,render_template
from pymongo import MongoClient
from flask_cors import CORS
from bson import ObjectId,json_util
from bson.errors import InvalidId
from flask_socketio import SocketIO, emit


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


app.config['TastyBites'] = 'Abha'
socketio = SocketIO(app, cors_allowed_origins="*",async_mode='threading')

client = MongoClient("mongodb+srv://abha25meshram:abha@cluster0.8v3gqht.mongodb.net/TastyBites?retryWrites=true&w=majority")
db = client["TastyBites"]
menu_collection = db["menu"]
cart_collection = db["cart"]
orders_collection = db["orders"]
auth_collection = db["auth"]



# Error handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad Request'}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not Found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method Not Allowed'}), 405

# Authentication
def authenticate(email, password):
    user = auth_collection.find_one({'email': email, 'password': password})
    return user is not None

def get_user(email):
    user = auth_collection.find_one({'email': email})
    user=dict(user)    
    user['_id'] = str(user['_id'])     
    return user

# POST Method for authentication (Login and Signup)
    
@app.route('/auth', methods=['POST'])
def authenticate_user():
    auth_info = request.json
    email = auth_info.get('email')
    password = auth_info.get('password')
    username = auth_info.get('username')
    is_signup = auth_info.get('signup', False)

    if is_signup:
        existing_user = auth_collection.find_one({'email': email})
        if existing_user:
            return jsonify({'message': 'Email already exists'}), 400

        del auth_info['signup']
        auth_collection.insert_one({'email': email, 'password': password, 'username': username})
        return jsonify({'message': 'Signup successful'}), 200

    existing_user = auth_collection.find_one({'email': email})
    if not existing_user:
        return jsonify({'message': 'Invalid credentials'}), 401

    if existing_user['password'] != password:
        return jsonify({'message': 'Invalid credentials'}), 401

    return jsonify({'message': 'Login successful', 'user_details': {'email': email, 'password': existing_user['password']}}), 200

@app.route("/menu", methods=["GET"])
def get_menu():
    availability = request.args.get("availability")
    search = request.args.get("search")
    print("Availability:", availability)
    print("Search:", search)

    query = {}
    if availability:
        if availability.lower() == "true":
            query["is_available"] = True
        elif availability.lower() == "false":
            query["is_available"] = False

    if search:
        query["dish_name"] = {"$regex": search, "$options": "i"}

    menu = list(menu_collection.find(query))

    for dish in menu:
        dish["_id"] = str(dish["_id"])

    return jsonify(menu)


# Add a new dish to the menu

#   "dish_id":2,
#   "dish_name":"idli",
#   "price":40,
#   "availability":"no"


@app.route("/menu", methods=["POST"])
def add_dish():
    new_dish = request.get_json()
    menu_collection.insert_one(new_dish)
    return jsonify({"message": "Dish added successfully"})


# Get a specific dish from the menu by dish ID
@app.route("/menu/<dish_id>", methods=["GET"])
def get_dish(dish_id):
    dish = menu_collection.find_one({"_id": ObjectId(dish_id)})
    if dish:
        dish["_id"] = str(dish["_id"])
        return jsonify(dish)
    else:
        return jsonify({"message": "Dish not found"})


# Update a dish in the menu
@app.route("/menu/<dish_id>", methods=["PUT"])
def update_dish(dish_id):
    updated_dish = request.get_json()
    menu_collection.update_one({"_id": ObjectId(dish_id)}, {"$set": updated_dish})
    return jsonify({"message": "Dish updated successfully"})


# Delete a dish from the menu
@app.route("/menu/<dish_id>", methods=["DELETE"])
def delete_dish(dish_id):
    menu_collection.delete_one({"_id": ObjectId(dish_id)})
    return jsonify({"message": "Dish deleted successfully"})


# Get cart items
@app.route('/orders', methods=['GET'])
def get_orders():
    orders = list(orders_collection.find())
    serialized_orders = json_util.dumps(orders)
    return serialized_orders, 200, {'Content-Type': 'application/json'}


# Add an item to the cart

@app.route("/orders", methods=["POST"])
def add_to_cart():
    item = request.get_json()
    dish_ids = item.get("dish_ids", [])
    customer_name = item.get("customer_name", "")

    # Validate dish IDs and fetch menu items
    valid_dish_ids = []
    ordered_dishes = []
    total_price = 0
    for dish_id in dish_ids:
        dish = menu_collection.find_one({"dish_id": dish_id, "availability": "yes"})
        if dish:
            valid_dish_ids.append(dish_id)
            ordered_dishes.append(dish)
            total_price += dish["price"]

    if not valid_dish_ids:
        return jsonify({"error": "Invalid dish IDs or dishes not available"})

    # Process the order
    order_id = len(list(orders_collection.find())) + 1
    order = {
        "order_id": order_id,
        "customer_name": customer_name,
        "dishes": ordered_dishes,
        "status": "pending",
        "total_price": total_price
    }
    orders_collection.insert_one(order)

    return jsonify({"message": "Order placed successfully", "order_id": order_id})

# @app.route("/")
# def index():
#     return render_template("index.html")

# Update an item in the cart


@app.route("/orders/<order_id>", methods=["PUT"])
def update_cart_item(order_id):
    try:
        # Validate the order_id
        if not order_id.isdigit():
            return jsonify({"error": "Invalid order ID"}), 400

        updated_item = request.get_json()
        orders_collection.update_one({"order_id": int(order_id)}, {"$set": updated_item})
        return jsonify({"message": "Order item updated successfully"})
    except ValueError:
        return jsonify({"error": "Invalid order ID"}), 400


@socketio.on('order_status_update')
def handle_order_status_update(updated_order):
    order_id = updated_order.get('order_id')
    status = updated_order.get('status')
    orders_collection.update_one({"order_id": order_id}, {"$set": {"status": status}})
    socketio.emit('order_status_update', updated_order, broadcast=True)




# Delete an item from the cart
@app.route("/orders/<int:order_id>", methods=["DELETE"])
def delete_from_cart(order_id):
    orders_collection.delete_one({"order_id": order_id})
    items = list(orders_collection.find())
    return jsonify({"message": "Item deleted from order successfully", "orderItems": items})




if __name__ == "__main__":
    CORS(app)
    socketio.run(app)
    app.run(host='localhost', port=8080,debug=True)

