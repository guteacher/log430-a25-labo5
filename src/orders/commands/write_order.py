"""
Orders (write-only model)
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""
import json
import requests
import xml.etree.ElementTree as ET
from orders.models.order import Order
from stocks.models.product import Product
from sqlalchemy.exc import SQLAlchemyError
from orders.models.order_item import OrderItem
from stocks.commands.write_stock import check_in_items_to_stock, check_out_items_from_stock, update_stock_redis
from db import get_sqlalchemy_session, get_redis_conn

def add_order(user_id: int, items: list):
    """Insert order with items in MySQL, keep Redis in sync"""
    if not items:
        raise ValueError("Cannot create order. An order must have 1 or more items.")

    product_ids = [item['product_id'] for item in items]
    session = get_sqlalchemy_session()

    try:
        products_query = session.query(Product).filter(Product.id.in_(product_ids)).all()
        price_map = {product.id: product.price for product in products_query}
        total_amount = 0
        order_items = []
        
        for item in items:
            pid = item["product_id"]
            qty = item["quantity"]

            if pid not in price_map:
                raise ValueError(f"Product ID {pid} not found in database.")

            unit_price = price_map[pid]
            total_amount += unit_price * qty

            order_items.append({
                'product_id': pid,
                'quantity': qty,
                'unit_price': unit_price
            })

        new_order = Order(user_id=user_id, total_amount=total_amount, payment_link=None)
        session.add(new_order)
        session.flush()   

        order_id = new_order.id

        new_order.payment_link = request_payment_link(new_order.id, total_amount, user_id)
        session.flush()  
        
        for item in order_items:
            order_item = OrderItem(
                order_id=order_id,
                product_id=item['product_id'],
                quantity=item['quantity'],
                unit_price=item['unit_price']
            )
            session.add(order_item)

        # Update stock
        check_out_items_from_stock(session, order_items)

        session.commit()

        # Insert order into Redis
        update_stock_redis(order_items, '-')
        add_order_to_redis(order_id, user_id, total_amount, items, new_order.payment_link)
        return order_id

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def modify_order(order_id: int, is_paid: bool):
    session = get_sqlalchemy_session()
    try:
        order = session.query(Order).filter(Order.id == order_id).first()

        if order is not None and is_paid is not None:
            order.is_paid = is_paid

        session.commit()
        session.refresh(order)
        return True
    except SQLAlchemyError as e:
        session.rollback()
        print(e)
        return False
    except Exception as e:
        session.rollback()
        print(e)
        return False
    finally:
        session.close()

def request_payment_link(order_id, total_amount, user_id):
    payment_id = 0
    payment_request = f"""
        <payment-request>
            <order-id>{order_id}</order-id>
            <amount>{total_amount}</amount>
            <user-id>{user_id}</user-id>
        </payment-request>
    """
    print("Make request to /payments/add")
    response = requests.post(
        'http://payments_web_service:5009/payments/add',
        data=payment_request,
        headers={'Content-Type': 'application/xml'}
    )
    print(f"Response from payments_service: {response.status_code}")
    if response.status_code == 200:
        root = ET.fromstring(response.text)
        payment_id = root.find('payment-id').text
        print(f"Payment ID: {payment_id}")

    return f"http://payments_web_service:5009/payments/pay/{payment_id}" 

def delete_order(order_id: int):
    """Delete order in MySQL, keep Redis in sync"""
    session = get_sqlalchemy_session()
    try:
        order = session.query(Order).filter(Order.id == order_id).first()
        if order:

            # MySQL
            order_items = session.query(OrderItem).filter(OrderItem.order_id == order_id).all()
            session.delete(order)
            check_in_items_to_stock(session, order_items)
            session.commit()

            # Redis
            update_stock_redis(order_items, '+')
            delete_order_from_redis(order_id)
            return 1  
        else:
            return 0  
            
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def add_order_to_redis(order_id, user_id, total_amount, items, payment_link):
    """Insert order to Redis"""
    r = get_redis_conn()
    r.hset(
        f"order:{order_id}",
        mapping={
            "user_id": user_id,
            "total_amount": float(total_amount),
            "items": json.dumps(items),
            "payment_link": payment_link
        }
    )

def delete_order_from_redis(order_id):
    """Delete order from Redis"""
    r = get_redis_conn()
    r.delete(f"order:{order_id}")