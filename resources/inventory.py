from flask_restful import Resource, reqparse
from flask import request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, InventoryItem, InventoryChange, AuditLog
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import bleach

class InventoryResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, required=True)
    parser.add_argument('category', type=str, required=True)
    parser.add_argument('quantity', type=int, required=True)
    parser.add_argument('min_quantity', type=int, default=5)
    parser.add_argument('unit_cost', type=float)
    parser.add_argument('description', type=str)
    parser.add_argument('supplier', type=str)
    
    update_parser = reqparse.RequestParser()
    update_parser.add_argument('quantity_adjustment', type=int)
    update_parser.add_argument('min_quantity', type=int)
    update_parser.add_argument('unit_cost', type=float)
    update_parser.add_argument('description', type=str)
    update_parser.add_argument('supplier', type=str)

    @jwt_required()
    def get(self, item_id=None):
        claims = get_jwt()
        if claims['role'] not in ['technician', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        if item_id:
            item = InventoryItem.query.get(item_id)
            if not item:
                return {"message": "Inventory item not found"}, 404
            return self.item_to_dict(item)
        
        # List inventory
        query = InventoryItem.query
        
        # Category filter
        category = request.args.get('category')
        if category:
            query = query.filter_by(category=category)
            
        # Low stock filter
        low_stock = request.args.get('low_stock')
        if low_stock and low_stock.lower() == 'true':
            query = query.filter(InventoryItem.quantity <= InventoryItem.min_quantity)
            
        items = query.order_by(InventoryItem.name).all()
        return [self.item_to_dict(i) for i in items]

    @jwt_required()
    def post(self):
        claims = get_jwt()
        if claims['role'] not in ['technician', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        data = self.parser.parse_args()
        
        # Check for duplicate
        if InventoryItem.query.filter_by(name=data['name']).first():
            return {"message": "Item already exists"}, 409
            
        # Create item
        item = InventoryItem(
            name=bleach.clean(data['name']),
            category=bleach.clean(data['category']),
            quantity=data['quantity'],
            min_quantity=data['min_quantity'],
            unit_cost=data.get('unit_cost'),
            description=bleach.clean(data['description']) if data.get('description') else None,
            supplier=bleach.clean(data['supplier']) if data.get('supplier') else None,
            last_restocked=datetime.now()
        )
        
        try:
            db.session.add(item)
            db.session.commit()
            
            # Create inventory change record
            change = InventoryChange(
                item=item,
                user_id=get_jwt_identity(),
                change_type='restock',
                quantity_change=data['quantity'],
                notes="Initial stock"
            )
            db.session.add(change)
            
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="INVENTORY_CREATE",
                target_id=item.id,
                target_type='inventory',
                details=f"Created item: {item.name}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.item_to_dict(item), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Inventory creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, item_id):
        claims = get_jwt()
        if claims['role'] not in ['technician', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        item = InventoryItem.query.get(item_id)
        if not item:
            return {"message": "Inventory item not found"}, 404
            
        data = self.update_parser.parse_args()
        changes = []
        change_notes = []
        
        # Update quantity
        if data.get('quantity_adjustment'):
            adjustment = data['quantity_adjustment']
            if adjustment != 0:
                item.quantity += adjustment
                change_type = 'restock' if adjustment > 0 else 'adjustment'
                
                # Record change
                change = InventoryChange(
                    item=item,
                    user_id=get_jwt_identity(),
                    change_type=change_type,
                    quantity_change=adjustment,
                    notes=f"Manual adjustment by user"
                )
                db.session.add(change)
                changes.append('quantity')
                change_notes.append(f"quantity adjusted by {adjustment}")
                
                # Update restock date if adding stock
                if adjustment > 0:
                    item.last_restocked = datetime.now()
                    changes.append('last_restocked')
        
        # Update other fields
        if data.get('min_quantity') is not None:
            item.min_quantity = data['min_quantity']
            changes.append('min_quantity')
        if data.get('unit_cost') is not None:
            item.unit_cost = data['unit_cost']
            changes.append('unit_cost')
        if data.get('description') is not None:
            item.description = bleach.clean(data['description']) if data['description'] else None
            changes.append('description')
        if data.get('supplier') is not None:
            item.supplier = bleach.clean(data['supplier']) if data['supplier'] else None
            changes.append('supplier')
            
        if not changes:
            return {"message": "No changes detected"}, 400
            
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="INVENTORY_UPDATE",
                target_id=item_id,
                details=f"Updated: {', '.join(changes)}. Notes: {'; '.join(change_notes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.item_to_dict(item)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Inventory update failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def delete(self, item_id):
        claims = get_jwt()
        if claims['role'] != 'admin':
            return {"message": "Admin access required"}, 403
            
        item = InventoryItem.query.get(item_id)
        if not item:
            return {"message": "Inventory item not found"}, 404
            
        try:
            # Record deletion in audit log before deleting
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="INVENTORY_DELETE",
                target_id=item_id,
                details=f"Deleted item: {item.name}"
            )
            db.session.add(audit)
            
            db.session.delete(item)
            db.session.commit()
            
            return {"message": "Inventory item deleted"}
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Inventory deletion failed: {str(e)}")
            return {"message": "Database error"}, 500

    def item_to_dict(self, item):
        return {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "quantity": item.quantity,
            "min_quantity": item.min_quantity,
            "unit_cost": item.unit_cost,
            "last_restocked": item.last_restocked.isoformat() if item.last_restocked else None,
            "low_stock": item.quantity <= item.min_quantity,
            "description": item.description,
            "supplier": item.supplier
        }