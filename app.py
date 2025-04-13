import os
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, SelectField, HiddenField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, InputRequired, Optional, Length

# --- App Configuration ---
app = Flask(__name__)

# Secret Key: Use environment variable in production, fallback for local dev
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-fallback-secret-key-CHANGE-FOR-PROD')

# Database URI: Use env var for Postgres on Render, fallback to local SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get('DATABASE_URL')
# Replace 'postgres://' with 'postgresql://' if DATABASE_URL starts with postgres:// (Heroku/older Render)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///' + os.path.join(basedir, 'local_tracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Models ---
class Food(db.Model):
    __tablename__ = 'foods'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    # Unit for which the nutrient values below are defined (e.g., 'g', 'ml', 'cup', 'scoop', 'slice')
    base_unit = db.Column(db.String(50), nullable=False)
    # The quantity of the base_unit (e.g., 100, 1)
    base_quantity = db.Column(db.Float, nullable=False, default=100.0)
    # Core nutrients per base_quantity of base_unit
    calories = db.Column(db.Float, nullable=False, default=0)
    protein = db.Column(db.Float, nullable=False, default=0)
    carbs = db.Column(db.Float, nullable=False, default=0)
    fat = db.Column(db.Float, nullable=False, default=0)
    fiber = db.Column(db.Float, nullable=True, default=0) # Optional field
    # Add other macros/micros as needed (e.g., sugar, sodium)
    notes = db.Column(db.Text, nullable=True) # Optional notes field

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to log entries
    logs = db.relationship('MealLog', backref='food', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Food {self.name}>'

class MealLog(db.Model):
    __tablename__ = 'meal_logs'
    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.Date, nullable=False, index=True)
    meal_type = db.Column(db.String(50), nullable=False) # e.g., 'Breakfast', 'Lunch'
    food_id = db.Column(db.Integer, db.ForeignKey('foods.id'), nullable=False)
    # Quantity CONSUMED in the food's defined 'base_unit'
    quantity_consumed = db.Column(db.Float, nullable=False)

    # Calculated values stored for efficiency
    calculated_calories = db.Column(db.Float, nullable=False)
    calculated_protein = db.Column(db.Float, nullable=False)
    calculated_carbs = db.Column(db.Float, nullable=False)
    calculated_fat = db.Column(db.Float, nullable=False)
    calculated_fiber = db.Column(db.Float, nullable=True)
    # Add other calculated fields matching Food model

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        food_name = self.food.name if self.food else 'Unknown Food'
        return f'<MealLog {self.quantity_consumed} {self.food.base_unit if self.food else ""} of {food_name} on {self.log_date}>'

# --- Forms ---
class FoodForm(FlaskForm):
    name = StringField('Food Name', validators=[DataRequired(), Length(max=150)])
    base_unit = StringField('Base Unit (e.g., g, ml, cup, slice)', validators=[DataRequired(), Length(max=50)])
    base_quantity = FloatField('Nutrients Defined Per this Quantity', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])
    calories = FloatField('Calories (kcal)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    protein = FloatField('Protein (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    carbs = FloatField('Carbohydrates (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fat = FloatField('Fat (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fiber = FloatField('Fiber (g)', default=0, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Food')

class LogEntryForm(FlaskForm):
    food_id = SelectField('Food Item', coerce=int, validators=[DataRequired()])
    quantity_consumed = FloatField('Quantity Consumed', validators=[DataRequired(), NumberRange(min=0.001)])
    # Hidden fields to pass context
    meal_type = HiddenField(validators=[DataRequired()])
    log_date = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Add to Log')

    # Needs dynamic population of food_id choices in the route
    def __init__(self, *args, **kwargs):
        super(LogEntryForm, self).__init__(*args, **kwargs)
        self.food_id.choices = [(f.id, f.name) for f in Food.query.order_by(Food.name).all()]


# --- Helper Functions ---
def calculate_nutrients(food, quantity_consumed):
    """Calculates nutrients based on the logged quantity."""
    results = {
        'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0, 'fiber': 0.0
        # Add keys for other nutrients tracked
    }
    if not food or food.base_quantity is None or food.base_quantity == 0 or quantity_consumed is None:
        return results # Safety check

    try:
        # Calculate the multiplier: (amount eaten) / (amount nutrients are defined for)
        multiplier = float(quantity_consumed) / float(food.base_quantity)

        # Helper to safely calculate and handle None/NaN/Infinity
        def safe_calc(nutrient_value, multiplier):
             if nutrient_value is None: return 0.0
             try:
                 val = float(nutrient_value) * multiplier
                 return val if isinstance(val, (int, float)) and abs(val) != float('inf') and val == val else 0.0
             except (TypeError, ValueError): return 0.0

        results['calories'] = safe_calc(food.calories, multiplier)
        results['protein']  = safe_calc(food.protein, multiplier)
        results['carbs']    = safe_calc(food.carbs, multiplier)
        results['fat']      = safe_calc(food.fat, multiplier)
        results['fiber']    = safe_calc(food.fiber, multiplier)
        # Calculate other nutrients here...

    except (TypeError, ValueError, ZeroDivisionError) as e:
        print(f"WARN: Error calculating nutrients: {e}")
        # Defaults are already set in results

    return results

def get_day_summary(log_date_obj):
    """Calculates total nutrients for a given date."""
    logs = MealLog.query.filter_by(log_date=log_date_obj).all()
    summary = { 'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0, 'fiber': 0 }
    for log in logs:
        summary['calories'] += log.calculated_calories or 0
        summary['protein'] += log.calculated_protein or 0
        summary['carbs'] += log.calculated_carbs or 0
        summary['fat'] += log.calculated_fat or 0
        summary['fiber'] += log.calculated_fiber or 0
        # Sum other nutrients...
    return summary

# --- Routes ---

# Main Route - Daily Log / Index
@app.route('/', methods=['GET', 'POST'])
def daily_log():
    log_date_str = request.args.get('date', date.today().isoformat())
    try:
        log_date_obj = date.fromisoformat(log_date_str)
    except ValueError:
        flash('Invalid date format. Showing today.', 'warning')
        log_date_obj = date.today()
        log_date_str = log_date_obj.isoformat()

    log_form = LogEntryForm(log_date=log_date_str) # Pass date to hidden field

    # Handle log entry submission
    if log_form.validate_on_submit():
        try:
            food = Food.query.get_or_404(log_form.food_id.data)
            quantity = log_form.quantity_consumed.data
            meal_type = log_form.meal_type.data # From hidden field
            current_log_date = date.fromisoformat(log_form.log_date.data) # From hidden field

            calculated = calculate_nutrients(food, quantity)

            new_log = MealLog(
                log_date=current_log_date,
                meal_type=meal_type,
                food_id=food.id,
                quantity_consumed=quantity,
                calculated_calories=calculated.get('calories', 0.0),
                calculated_protein=calculated.get('protein', 0.0),
                calculated_carbs=calculated.get('carbs', 0.0),
                calculated_fat=calculated.get('fat', 0.0),
                calculated_fiber=calculated.get('fiber', 0.0)
                # Add other calculated values...
            )
            db.session.add(new_log)
            db.session.commit()
            flash(f'Added {quantity} {food.base_unit} of {food.name} to {meal_type}.', 'success')
            return redirect(url_for('daily_log', date=current_log_date.isoformat()))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding log entry: {e}', 'danger')

    # Data for displaying the page (GET request or after failed POST)
    logs_by_meal = {}
    meal_types = ['Breakfast', 'Lunch', 'Dinner', 'Snacks']
    for meal in meal_types:
        logs_by_meal[meal] = MealLog.query.filter_by(log_date=log_date_obj, meal_type=meal)\
                                       .order_by(MealLog.created_at)\
                                       .options(db.joinedload(MealLog.food)).all() # Eager load food details

    daily_summary = get_day_summary(log_date_obj)
    prev_date = (log_date_obj - timedelta(days=1)).isoformat()
    next_date = (log_date_obj + timedelta(days=1)).isoformat()

    return render_template('daily_log.html',
                           log_form=log_form, # Pass the form object
                           current_date_str=log_date_str,
                           current_date_obj=log_date_obj,
                           prev_date=prev_date,
                           next_date=next_date,
                           logs_by_meal=logs_by_meal,
                           daily_summary=daily_summary,
                           meal_types=meal_types)

# Delete Log Entry
@app.route('/log/delete/<int:log_id>', methods=['POST'])
def delete_log_entry(log_id):
    log_entry = MealLog.query.get_or_404(log_id)
    log_date_str = log_entry.log_date.isoformat() # Get date before deleting
    try:
        db.session.delete(log_entry)
        db.session.commit()
        flash('Log entry deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting log entry: {e}', 'danger')
    return redirect(url_for('daily_log', date=log_date_str))


# Database View Route
@app.route('/database')
def database_view():
    foods = Food.query.order_by(Food.name).all()
    return render_template('database_view.html', foods=foods)

# Add Food Route
@app.route('/database/add', methods=['GET', 'POST'])
def add_food():
    form = FoodForm()
    if form.validate_on_submit():
        existing_food = Food.query.filter(db.func.lower(Food.name) == form.name.data.strip().lower()).first()
        if existing_food:
            flash('A food item with this name already exists.', 'danger')
        else:
            try:
                new_food = Food(
                    name=form.name.data.strip(),
                    base_unit=form.base_unit.data.strip(),
                    base_quantity=form.base_quantity.data,
                    calories=form.calories.data,
                    protein=form.protein.data,
                    carbs=form.carbs.data,
                    fat=form.fat.data,
                    fiber=form.fiber.data,
                    notes=form.notes.data
                    # Add other fields...
                )
                db.session.add(new_food)
                db.session.commit()
                flash(f'Food item "{new_food.name}" added successfully!', 'success')
                return redirect(url_for('database_view'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding food: {e}', 'danger')
    return render_template('add_edit_food.html', form=form, title='Add New Food Item', action_url=url_for('add_food'))

# Edit Food Route
@app.route('/database/edit/<int:food_id>', methods=['GET', 'POST'])
def edit_food(food_id):
    food = Food.query.get_or_404(food_id)
    form = FoodForm(obj=food) # Pre-populate form with existing data
    if form.validate_on_submit():
        new_name_lower = form.name.data.strip().lower()
        existing_food_conflict = Food.query.filter(
            db.func.lower(Food.name) == new_name_lower,
            Food.id != food_id # Check names except the current item
        ).first()
        if existing_food_conflict:
             flash('Another food item with this name already exists.', 'danger')
        else:
            try:
                food.name = form.name.data.strip()
                food.base_unit = form.base_unit.data.strip()
                food.base_quantity=form.base_quantity.data
                food.calories=form.calories.data
                food.protein=form.protein.data
                food.carbs=form.carbs.data
                food.fat=form.fat.data
                food.fiber=form.fiber.data
                food.notes=form.notes.data
                # Update other fields...
                food.updated_at = datetime.utcnow()
                db.session.commit()
                flash(f'Food item "{food.name}" updated successfully!', 'success')
                return redirect(url_for('database_view'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating food: {e}', 'danger')
    return render_template('add_edit_food.html', form=form, title=f'Edit Food: {food.name}', action_url=url_for('edit_food', food_id=food_id))

# Delete Food Route
@app.route('/database/delete/<int:food_id>', methods=['POST'])
def delete_food(food_id):
    food = Food.query.get_or_404(food_id)
    food_name = food.name
    try:
        db.session.delete(food) # Cascade should delete related logs
        db.session.commit()
        flash(f'Food item "{food_name}" and all its log entries deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting food: {e}', 'danger')
    return redirect(url_for('database_view'))

# --- Initialize Database (Run once or use migrations) ---
# This is simple for initial setup. For production/updates, use Flask-Migrate.
with app.app_context():
    print("Attempting to create database tables (if they don't exist)...")
    try:
        db.create_all()
        print("Database tables checked/created.")
    except Exception as e:
        print(f"Error creating database tables: {e}")
        print("If using PostgreSQL, ensure the database exists and connection URL is correct.")
        print("You might need to manually create the DB or user/permissions.")

# --- Run the App (for local development only) ---
if __name__ == '__main__':
    # Note: host='0.0.0.0' makes it accessible on your local network
    # Remove debug=True before deployment!
    print("Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
