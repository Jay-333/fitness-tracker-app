import os
# import requests # Removed as requested
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify # Added jsonify just in case
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, SelectField, HiddenField, TextAreaField, SelectMultipleField
from wtforms.validators import DataRequired, NumberRange, InputRequired, Optional, Length, ValidationError # Added ValidationError
from wtforms.widgets import ListWidget, CheckboxInput
import math
from flask_migrate import Migrate # Keep for migrations
from sqlalchemy import CheckConstraint, MetaData # Keep for migrations

# --- App Configuration ---
app = Flask(__name__)

# --- Naming Convention (Essential for Alembic/Migrate) ---
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s", # Use constraint_name for CHECK
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)

# Secret Key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-fallback-secret-key-CHANGE-FOR-PROD')

# Database URI
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///' + os.path.join(basedir, 'local_tracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize DB and Migrate ---
db = SQLAlchemy(app, metadata=metadata) # Apply metadata with convention
migrate = Migrate(app, db)

# --- Database Models ---

# Forward declaration for type hints if needed (usually not necessary here)
# class MealLog: pass
# class RecipeIngredient: pass
# class Ingredient: pass

class Food(db.Model):
    __tablename__ = 'foods'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False) # Unique constraint implied index
    base_unit = db.Column(db.String(50), nullable=False)
    base_quantity = db.Column(db.Float, nullable=False, default=100.0)
    calories = db.Column(db.Float, nullable=False, default=0)
    protein = db.Column(db.Float, nullable=False, default=0)
    carbs = db.Column(db.Float, nullable=False, default=0)
    fat = db.Column(db.Float, nullable=False, default=0)
    fiber = db.Column(db.Float, nullable=True, default=0)
    sugar = db.Column(db.Float, nullable=True, default=0)    # Added
    calcium = db.Column(db.Float, nullable=True, default=0) # Added
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to MealLog entries using this specific Food item
    # 'backref="food"' creates the 'food' attribute on MealLog instances
    logs = db.relationship('MealLog', backref='food', lazy='select', cascade="all, delete-orphan") # Changed lazy to select (default)

    def __repr__(self): return f'<Food {self.name}>'


class Ingredient(db.Model):
    __tablename__ = 'ingredients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    category = db.Column(db.String(100), nullable=True)
    typical_unit = db.Column(db.String(50), nullable=False, default='g')
    unit_quantity = db.Column(db.Float, nullable=False, default=100.0)
    calories = db.Column(db.Float, nullable=True)
    protein = db.Column(db.Float, nullable=True)
    carbs = db.Column(db.Float, nullable=True)
    fat = db.Column(db.Float, nullable=True)
    fiber = db.Column(db.Float, nullable=True)
    sugar = db.Column(db.Float, nullable=True)    # Added
    calcium = db.Column(db.Float, nullable=True) # Added
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship: Where is this ingredient used?
    # Access via ingredient.recipes_where_used (list of RecipeIngredient links)
    # 'backref="ingredient"' creates 'ingredient' attribute on RecipeIngredient instances
    recipes_where_used = db.relationship('RecipeIngredient', backref='ingredient', lazy='select') # Renamed for clarity, using default lazy

    def __repr__(self): return f'<Ingredient {self.name}>'


class Recipe(db.Model):
    __tablename__ = 'recipes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    meal_type_suitability = db.Column(db.String(100), nullable=True, default='Any')
    total_calories = db.Column(db.Float, nullable=True)
    total_protein = db.Column(db.Float, nullable=True)
    total_carbs = db.Column(db.Float, nullable=True)
    total_fat = db.Column(db.Float, nullable=True)
    total_fiber = db.Column(db.Float, nullable=True)
    total_sugar = db.Column(db.Float, nullable=True)    # Added
    total_calcium = db.Column(db.Float, nullable=True) # Added
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship: Ingredients in this recipe
    # Access via recipe.ingredients (list of RecipeIngredient links)
    # 'backref="recipe"' creates 'recipe' attribute on RecipeIngredient instances
    ingredients = db.relationship('RecipeIngredient', backref='recipe', lazy='select', cascade='all, delete-orphan') # Changed lazy

    # Relationship: Logs where this recipe was recorded
    # Access via recipe.logs (list of MealLog entries)
    # 'backref="recipe"' creates 'recipe' attribute on MealLog instances
    logs = db.relationship('MealLog', backref='recipe', lazy='select') # Added relationship

    def __repr__(self): return f'<Recipe {self.name}>'


class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredients.id'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False) # Qty in ingredient's typical_unit

    # The 'recipe' attribute is created by backref from Recipe.ingredients
    # The 'ingredient' attribute is created by backref from Ingredient.recipes_where_used

    def __repr__(self):
        # Use relationships defined via backrefs
        ing_name = self.ingredient.name if hasattr(self, 'ingredient') and self.ingredient else '?'
        unit = self.ingredient.typical_unit if hasattr(self, 'ingredient') and self.ingredient else 'unit'
        rec_id = self.recipe.id if hasattr(self, 'recipe') and self.recipe else '?'
        return f'<{self.quantity} {unit} of {ing_name} in Recipe {rec_id}>'


class MealLog(db.Model):
    __tablename__ = 'meal_logs'
    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.Date, nullable=False, index=True)
    meal_type = db.Column(db.String(50), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey('foods.id'), nullable=True)     # Nullable ok
    recipe_id =db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True) # Nullable ok
    quantity_consumed = db.Column(db.Float, nullable=False) # For Food: in base_unit; For Recipe: multiplier/servings
    calculated_calories = db.Column(db.Float, nullable=False)
    calculated_protein = db.Column(db.Float, nullable=False)
    calculated_carbs = db.Column(db.Float, nullable=False)
    calculated_fat = db.Column(db.Float, nullable=False)
    calculated_fiber = db.Column(db.Float, nullable=True)
    calculated_sugar = db.Column(db.Float, nullable=True)    # Added
    calculated_calcium = db.Column(db.Float, nullable=True) # Added
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships 'food' and 'recipe' are now defined via backrefs from Food and Recipe models.
    # DO NOT redefine them here explicitly.

    __table_args__ = (
        db.CheckConstraint(
            '(food_id IS NOT NULL AND recipe_id IS NULL) OR (food_id IS NULL AND recipe_id IS NOT NULL)',
            name='meal_log_source_check' # Name is required for Alembic
        ),
    )

    def __repr__(self):
        # Check relationship attributes created by backrefs
        if hasattr(self, 'food') and self.food:
            item_name = self.food.name
            unit = self.food.base_unit
            return f'<MealLog {self.quantity_consumed} {unit} of Food: {item_name} on {self.log_date}>'
        elif hasattr(self, 'recipe') and self.recipe:
            item_name = self.recipe.name
            unit_str = f'{self.quantity_consumed} {"serving" if self.quantity_consumed == 1 else "servings"}'
            return f'<MealLog {unit_str} of Recipe: {item_name} on {self.log_date}>'
        else: # Should not happen if constraint works
            return f'<MealLog ID {self.id} log_date={self.log_date} - Invalid State (no food/recipe link)>'


# --- Forms ---

class IngredientForm(FlaskForm):
    name = StringField('Ingredient Name', validators=[DataRequired(), Length(max=150)])
    category = StringField('Category', validators=[Optional(), Length(max=100)], description="e.g., Vegetable, Protein, Grain")
    typical_unit = StringField('Typical Unit for Recipes', default='g', validators=[DataRequired(), Length(max=50)], description="e.g., g, ml, piece, cup, slice")
    unit_quantity = FloatField('Nutrients Defined Per this Quantity of Unit', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])
    calories = FloatField('Est. Calories (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    protein = FloatField('Est. Protein (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    carbs = FloatField('Est. Carbs (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    fat = FloatField('Est. Fat (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    fiber = FloatField('Est. Fiber (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    sugar = FloatField('Est. Sugar(g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])     # Added
    calcium = FloatField('Est. calcium(mg?) (per defined Qty)', validators=[Optional(), NumberRange(min=0)]) # Added (clarify unit?)
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Ingredient')

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description (Optional)')
    instructions = TextAreaField('Instructions (Optional)')
    meal_type_suitability = SelectMultipleField(
        'Suitable for Meals (Optional)',
        choices=[('Breakfast','Breakfast'), ('Lunch','Lunch'), ('Dinner','Dinner'), ('Snack','Snack'), ('Any','Any')],
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()],
        description="Select one or more applicable meal types."
    )
    submit = SubmitField('Save Recipe Details')

class AddIngredientToRecipeForm(FlaskForm):
    ingredient_id = SelectField('Ingredient', coerce=int, validators=[DataRequired()])
    quantity = FloatField('Quantity', validators=[InputRequired(), NumberRange(min=0.001)])
    submit = SubmitField('Add Ingredient')

class FoodForm(FlaskForm):
    name = StringField('Food Name', validators=[DataRequired(), Length(max=150)])
    base_unit = StringField('Base Unit (e.g., g, ml, cup, slice)', validators=[DataRequired(), Length(max=50)])
    base_quantity = FloatField('Nutrients Defined Per this Quantity', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])
    calories = FloatField('Calories (kcal)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    protein = FloatField('Protein (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    carbs = FloatField('Carbohydrates (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fat = FloatField('Fat (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fiber = FloatField('Fiber (g)', default=0, validators=[Optional(), NumberRange(min=0)])
    sugar = FloatField('Sugar (g)', default=0, validators=[Optional(), NumberRange(min=0)])     # Added
    calcium = FloatField('Calcium (mg)', default=0, validators=[Optional(), NumberRange(min=0)]) # Added
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Food')

class LogEntryForm(FlaskForm): # For logging individual foods
    food_id = SelectField('Food Item', coerce=int, validators=[DataRequired()])
    quantity_consumed = FloatField('Quantity Consumed', validators=[DataRequired(), NumberRange(min=0.001)])
    meal_type = HiddenField(validators=[DataRequired()])
    log_date = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Add to Log')

    def __init__(self, *args, **kwargs):
        super(LogEntryForm, self).__init__(*args, **kwargs)
        # Populate choices dynamically
        try:
            # This query runs when the form is instantiated. Consider if this is too slow with many foods.
            self.food_id.choices = [(f.id, f.name) for f in Food.query.order_by(Food.name).all()]
        except Exception as e:
            # Handle cases where DB might not be ready during initialization (e.g., during migrations)
            print(f"Warning: Could not populate Food choices during LogEntryForm init: {e}")
            self.food_id.choices = []


class LogRecipeForm(FlaskForm):
    recipe_id = SelectField('Recipe', coerce=int, validators=[DataRequired()])
    quantity_consumed = FloatField('Servings / Multiplier', default=1.0, validators=[InputRequired(), NumberRange(min=0.01)], description="e.g., 1 for whole recipe, 0.5 for half")
    meal_type = HiddenField(validators=[DataRequired()])
    log_date = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Log Recipe')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate choices dynamically
        try:
             self.recipe_id.choices = [(r.id, r.name) for r in Recipe.query.order_by(Recipe.name).all()]
        except Exception as e:
            print(f"Warning: Could not populate Recipe choices during LogRecipeForm init: {e}")
            self.recipe_id.choices = []


# --- Helper Functions ---
def calculate_recipe_nutrition(recipe_id):
    """Calculates and returns total estimated nutrition for a given recipe ID."""
    # Added sugar and calcium
    totals = {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0, 'fiber': 0.0, 'sugar': 0.0, 'calcium': 0.0}
    recipe = Recipe.query.get(recipe_id)
    if not recipe: return None

    # Access relationship. No need for .all() if lazy='select' or eager loaded.
    # Use relationship name from RecipeIngredient -> Ingredient ('ingredient')
    recipe_ingredients = recipe.ingredients

    for ri in recipe_ingredients:
        ingredient = ri.ingredient # Access via relationship
        if not ingredient: # Defensive check
            print(f"WARN: Could not find ingredient details for RecipeIngredient ID {ri.id}")
            continue

        quantity_used = ri.quantity

        if ingredient.unit_quantity is None or ingredient.unit_quantity == 0:
            print(f"WARN: Skipping {ingredient.name} in recipe {recipe.id}, invalid unit_quantity.")
            continue

        try: multiplier = float(quantity_used) / float(ingredient.unit_quantity)
        except (ValueError, TypeError, ZeroDivisionError):
            print(f"WARN: Cannot calculate multiplier for {ingredient.name} in recipe {recipe.id}. Skipping.")
            continue

        def safe_get(val): return float(val) if val is not None else 0.0

        totals['calories'] += (safe_get(ingredient.calories) * multiplier)
        totals['protein']  += (safe_get(ingredient.protein) * multiplier)
        totals['carbs']    += (safe_get(ingredient.carbs) * multiplier)
        totals['fat']      += (safe_get(ingredient.fat) * multiplier)
        totals['fiber']    += (safe_get(ingredient.fiber) * multiplier)
        totals['sugar']    += (safe_get(ingredient.sugar) * multiplier)   # Added
        totals['calcium']  += (safe_get(ingredient.calcium) * multiplier) # Added

    for key in totals: # Ensure finite numbers
        if not isinstance(totals[key], (int, float)) or not math.isfinite(totals[key]): totals[key] = 0.0

    return totals

def calculate_nutrients(food, quantity_consumed):
    """Calculates nutrients for a specific food log entry."""
    # Added sugar and calcium
    results = {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0, 'fiber': 0.0, 'sugar': 0.0, 'calcium': 0.0}
    if not food or food.base_quantity is None or food.base_quantity == 0 or quantity_consumed is None: return results

    try:
        multiplier = float(quantity_consumed) / float(food.base_quantity)

        def safe_calc(val, mult):
             if val is None: return 0.0
             try:
                 res = float(val) * mult
                 return res if isinstance(res, (int, float)) and math.isfinite(res) else 0.0
             except (TypeError, ValueError): return 0.0

        results['calories'] = safe_calc(food.calories, multiplier)
        results['protein']  = safe_calc(food.protein, multiplier)
        results['carbs']    = safe_calc(food.carbs, multiplier)
        results['fat']      = safe_calc(food.fat, multiplier)
        results['fiber']    = safe_calc(food.fiber, multiplier)
        results['sugar']    = safe_calc(food.sugar, multiplier)   # Added
        results['calcium']  = safe_calc(food.calcium, multiplier) # Added

    except (TypeError, ValueError, ZeroDivisionError) as e: print(f"WARN: Error calculating food nutrients: {e}")
    return results

def get_day_summary(log_date_obj):
    """Calculates total nutrients for a given date."""
    # Use eager loading to prevent N+1 queries when checking log type in loop (optional but good)
    logs = MealLog.query.filter_by(log_date=log_date_obj).options(
        db.joinedload(MealLog.food), db.joinedload(MealLog.recipe)
        ).all()
    # Added sugar and calcium
    summary = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0, 'fiber': 0, 'sugar': 0, 'calcium': 0}
    for log in logs:
        summary['calories'] += log.calculated_calories or 0
        summary['protein'] += log.calculated_protein or 0
        summary['carbs'] += log.calculated_carbs or 0
        summary['fat'] += log.calculated_fat or 0
        summary['fiber'] += log.calculated_fiber or 0
        summary['sugar'] += log.calculated_sugar or 0     # Added
        summary['calcium'] += log.calculated_calcium or 0 # Added
    return summary

# --- Routes ---

@app.route('/', methods=['GET']) # Redirect root to today's log
def index():
     return redirect(url_for('daily_log', date=date.today().isoformat()))

@app.route('/log', methods=['GET']) # Keep original route too
def daily_log():
    log_date_str = request.args.get('date', date.today().isoformat())
    try:
        log_date_obj = date.fromisoformat(log_date_str)
    except ValueError:
        flash('Invalid date format. Showing today.', 'warning')
        log_date_obj = date.today()
        log_date_str = log_date_obj.isoformat()

    # Instantiate forms
    log_food_form = LogEntryForm(log_date=log_date_str)
    log_recipe_form = LogRecipeForm(log_date=log_date_str)

    # Fetch data for display
    logs_by_meal = {}
    meal_types = ['Breakfast', 'Lunch', 'Dinner', 'Snacks']
    for meal in meal_types:
        logs_by_meal[meal] = MealLog.query.filter_by(log_date=log_date_obj, meal_type=meal)\
                                       .order_by(MealLog.created_at)\
                                       .options(db.joinedload(MealLog.food), # Eager load food
                                                db.joinedload(MealLog.recipe)).all() # Eager load recipe

    daily_summary = get_day_summary(log_date_obj)
    prev_date = (log_date_obj - timedelta(days=1)).isoformat()
    next_date = (log_date_obj + timedelta(days=1)).isoformat()

    return render_template('daily_log.html',
                           log_form=log_food_form,
                           log_recipe_form=log_recipe_form,
                           current_date_str=log_date_str,
                           current_date_obj=log_date_obj,
                           prev_date=prev_date,
                           next_date=next_date,
                           logs_by_meal=logs_by_meal,
                           daily_summary=daily_summary,
                           meal_types=meal_types)

@app.route('/log/food', methods=['POST']) # Separate route for food logging
def log_food_entry():
    form = LogEntryForm(request.form)
    log_date_str = form.log_date.data or date.today().isoformat() # For redirect

    # Repopulate choices needed for validation if failed
    if not form.food_id.choices:
         form.food_id.choices = [(f.id, f.name) for f in Food.query.order_by(Food.name).all()]


    if form.validate_on_submit():
        try:
            food = Food.query.get_or_404(form.food_id.data)
            quantity = form.quantity_consumed.data
            meal_type = form.meal_type.data
            current_log_date = date.fromisoformat(log_date_str)

            calculated = calculate_nutrients(food, quantity)

            new_log = MealLog(
                log_date=current_log_date,
                meal_type=meal_type,
                food_id=food.id, # Set food_id
                recipe_id=None,  # Ensure recipe_id is None
                quantity_consumed=quantity,
                calculated_calories=calculated.get('calories', 0.0),
                calculated_protein=calculated.get('protein', 0.0),
                calculated_carbs=calculated.get('carbs', 0.0),
                calculated_fat=calculated.get('fat', 0.0),
                calculated_fiber=calculated.get('fiber', 0.0),
                calculated_sugar=calculated.get('sugar', 0.0),    # Added
                calculated_calcium=calculated.get('calcium', 0.0) # Added
            )
            db.session.add(new_log)
            db.session.commit()
            flash(f'Added {quantity} {food.base_unit} of {food.name} to {meal_type}.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding log entry: {e}', 'danger')
            print(f"ERROR logging food: {e}") # Print for debugging
    else:
        # Handle validation errors
        error_messages = [f"{f.label.text}: {e}" for f, errs in form.errors.items() for e in errs]
        flash("Could not log food: " + "; ".join(error_messages), "danger")

    return redirect(url_for('daily_log', date=log_date_str))


@app.route('/log/recipe', methods=['POST'])
def log_recipe_entry():
    form = LogRecipeForm(request.form)
    log_date_str = form.log_date.data or date.today().isoformat()

    # Repopulate choices for validation
    if not form.recipe_id.choices:
        form.recipe_id.choices = [(r.id, r.name) for r in Recipe.query.order_by(Recipe.name).all()]

    if form.validate_on_submit():
        try:
            recipe_id = form.recipe_id.data
            quantity = form.quantity_consumed.data # Serving multiplier
            meal_type = form.meal_type.data
            current_log_date = date.fromisoformat(log_date_str)

            recipe = Recipe.query.get(recipe_id)
            if not recipe: raise ValueError("Recipe not found")

            # Use pre-calculated recipe totals, handle None
            rcp_cal = recipe.total_calories or 0.0
            rcp_pro = recipe.total_protein or 0.0
            rcp_car = recipe.total_carbs or 0.0
            rcp_fat = recipe.total_fat or 0.0
            rcp_fib = recipe.total_fiber or 0.0
            rcp_sug = recipe.total_sugar or 0.0     # Added
            rcp_calcium = recipe.total_calcium or 0.0 # Added

            # Calculate portion
            portion_cal = rcp_cal * quantity
            portion_pro = rcp_pro * quantity
            portion_car = rcp_car * quantity
            portion_fat = rcp_fat * quantity
            portion_fib = rcp_fib * quantity
            portion_sug = rcp_sug * quantity       # Added
            portion_calcium = rcp_calcium * quantity # Added

            new_log = MealLog(
                log_date=current_log_date,
                meal_type=meal_type,
                recipe_id=recipe.id, # Set recipe_id
                food_id=None,      # Ensure food_id is None
                quantity_consumed=quantity, # Store servings multiplier
                calculated_calories=portion_cal,
                calculated_protein=portion_pro,
                calculated_carbs=portion_car,
                calculated_fat=portion_fat,
                calculated_fiber=portion_fib,
                calculated_sugar=portion_sug,      # Added
                calculated_calcium=portion_calcium # Added
            )
            db.session.add(new_log)
            db.session.commit()

            serv_str = f'{quantity} {"serving" if quantity == 1 else "servings"}'
            flash(f'Logged {serv_str} of recipe "{recipe.name}" to {meal_type}.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error logging recipe entry: {e}', 'danger')
            print(f"ERROR logging recipe: {e}")
    else:
        error_messages = [f"{f.label.text}: {e}" for f, errs in form.errors.items() for e in errs]
        flash("Could not log recipe: " + "; ".join(error_messages), "danger")

    return redirect(url_for('daily_log', date=log_date_str))

@app.route('/log/delete/<int:log_id>', methods=['POST'])
def delete_log_entry(log_id):
    # ... (Keep existing code, should work fine) ...
    log_entry = MealLog.query.get_or_404(log_id)
    log_date_str = log_entry.log_date.isoformat()
    try:
        db.session.delete(log_entry)
        db.session.commit()
        flash('Log entry deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting log entry: {e}', 'danger')
    return redirect(url_for('daily_log', date=log_date_str))

# --- Food Database Routes (Manual Entry) ---
@app.route('/database')
def database_view():
    foods = Food.query.order_by(Food.name).all()
    return render_template('database_view.html', foods=foods)

@app.route('/database/add', methods=['GET', 'POST'])
def add_food():
    form = FoodForm()
    if form.validate_on_submit():
        # ... (Keep existing logic, ensure new fields are saved) ...
        existing_food = Food.query.filter(db.func.lower(Food.name) == form.name.data.strip().lower()).first()
        if existing_food: flash('Food item already exists.', 'danger')
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
                    fiber=form.fiber.data if form.fiber.data is not None else None,
                    sugar=form.sugar.data if form.sugar.data is not None else None,     # Added
                    calcium=form.calcium.data if form.calcium.data is not None else None, # Added
                    notes=form.notes.data
                )
                db.session.add(new_food)
                db.session.commit()
                flash(f'Food item "{new_food.name}" added.', 'success')
                return redirect(url_for('database_view'))
            except Exception as e:
                db.session.rollback(); flash(f'Error adding food: {e}', 'danger')
    return render_template('add_edit_food.html', form=form, title='Add New Food Item', action_url=url_for('add_food'))

@app.route('/database/edit/<int:food_id>', methods=['GET', 'POST'])
def edit_food(food_id):
    food = Food.query.get_or_404(food_id)
    form = FoodForm(obj=food)
    if form.validate_on_submit():
        # ... (Keep existing logic, ensure new fields are updated) ...
        new_name_lower = form.name.data.strip().lower()
        existing = Food.query.filter(db.func.lower(Food.name) == new_name_lower, Food.id != food_id).first()
        if existing: flash('Another food item has this name.', 'danger')
        else:
            try:
                food.name = form.name.data.strip()
                food.base_unit = form.base_unit.data.strip()
                food.base_quantity = form.base_quantity.data
                food.calories = form.calories.data
                food.protein = form.protein.data
                food.carbs = form.carbs.data
                food.fat = form.fat.data
                food.fiber = form.fiber.data if form.fiber.data is not None else None
                food.sugar = form.sugar.data if form.sugar.data is not None else None     # Added
                food.calcium = form.calcium.data if form.calcium.data is not None else None # Added
                food.notes = form.notes.data
                food.updated_at = datetime.utcnow()
                db.session.commit()
                flash(f'Food item "{food.name}" updated.', 'success')
                return redirect(url_for('database_view'))
            except Exception as e:
                db.session.rollback(); flash(f'Error updating food: {e}', 'danger')
    return render_template('add_edit_food.html', form=form, title=f'Edit Food: {food.name}', action_url=url_for('edit_food', food_id=food_id))

@app.route('/database/delete/<int:food_id>', methods=['POST'])
def delete_food(food_id):
    # ... (Keep existing code) ...
    food = Food.query.get_or_404(food_id)
    try:
        db.session.delete(food) # Cascade delete logs
        db.session.commit()
        flash(f'Food item "{food.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Error deleting food: {e}', 'danger')
    return redirect(url_for('database_view'))


# --- Ingredient Management Routes ---
@app.route('/ingredients')
def ingredients_list():
    # ... (Keep existing code) ...
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    return render_template('ingredients_list.html', ingredients=ingredients)

@app.route('/ingredients/add', methods=['GET', 'POST'])
def add_ingredient():
    form = IngredientForm()
    if form.validate_on_submit():
        # ... (Keep existing logic, ensure new fields are saved) ...
        existing = Ingredient.query.filter(db.func.lower(Ingredient.name) == form.name.data.strip().lower()).first()
        if existing: flash('Ingredient already exists.', 'danger')
        else:
            try:
                new_ingredient = Ingredient(
                    name=form.name.data.strip(),
                    category=form.category.data.strip() if form.category.data else None,
                    typical_unit=form.typical_unit.data.strip(),
                    unit_quantity=form.unit_quantity.data,
                    calories=form.calories.data if form.calories.data is not None else None,
                    protein=form.protein.data if form.protein.data is not None else None,
                    carbs=form.carbs.data if form.carbs.data is not None else None,
                    fat=form.fat.data if form.fat.data is not None else None,
                    fiber=form.fiber.data if form.fiber.data is not None else None,
                    sugar=form.sugar.data if form.sugar.data is not None else None,       # Added
                    calcium=form.calcium.data if form.calcium.data is not None else None,   # Added
                    notes=form.notes.data
                    # updated_at handled by default/onupdate
                )
                db.session.add(new_ingredient)
                db.session.commit()
                flash(f'Ingredient "{new_ingredient.name}" added.', 'success')
                return redirect(url_for('ingredients_list'))
            except Exception as e:
                db.session.rollback(); flash(f'Error adding ingredient: {e}', 'danger')
    return render_template('add_edit_ingredient.html',
                           form=form,
                           title='Add New Ingredient',
                           action_url=url_for('add_ingredient'))

@app.route('/ingredients/edit/<int:ingredient_id>', methods=['GET', 'POST'])
def edit_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    form = IngredientForm(obj=ingredient)
    if form.validate_on_submit():
        # ... (Keep existing logic, ensure new fields are updated) ...
        new_name_lower = form.name.data.strip().lower()
        existing = Ingredient.query.filter(db.func.lower(Ingredient.name) == new_name_lower, Ingredient.id != ingredient_id).first()
        if existing: flash('Another ingredient has this name.', 'danger')
        else:
            try:
                ingredient.name = form.name.data.strip()
                ingredient.category = form.category.data.strip() if form.category.data else None
                ingredient.typical_unit = form.typical_unit.data.strip()
                ingredient.unit_quantity = form.unit_quantity.data
                ingredient.calories = form.calories.data if form.calories.data is not None else None
                ingredient.protein = form.protein.data if form.protein.data is not None else None
                ingredient.carbs = form.carbs.data if form.carbs.data is not None else None
                ingredient.fat = form.fat.data if form.fat.data is not None else None
                ingredient.fiber = form.fiber.data if form.fiber.data is not None else None
                ingredient.sugar = form.sugar.data if form.sugar.data is not None else None       # Added
                ingredient.calcium = form.calcium.data if form.calcium.data is not None else None   # Added
                ingredient.notes = form.notes.data
                ingredient.updated_at = datetime.utcnow()
                db.session.commit()
                flash(f'Ingredient "{ingredient.name}" updated.', 'success')
                return redirect(url_for('ingredients_list'))
            except Exception as e:
                db.session.rollback(); flash(f'Error updating ingredient: {e}', 'danger')
    return render_template('add_edit_ingredient.html',
                           form=form,
                           title=f'Edit Ingredient: {ingredient.name}',
                           action_url=url_for('edit_ingredient', ingredient_id=ingredient_id))

@app.route('/ingredients/delete/<int:ingredient_id>', methods=['POST'])
def delete_ingredient(ingredient_id):
    # ... (Keep existing code) ...
     ingredient = Ingredient.query.get_or_404(ingredient_id)
     # Check if used in recipes before deleting? Important later.
     # recipe_links = ingredient.recipes_where_used.count() # Count links
     # if recipe_links > 0: flash(...) return redirect...
     try:
         db.session.delete(ingredient)
         db.session.commit()
         flash(f'Ingredient "{ingredient.name}" deleted.', 'success')
     except Exception as e:
         db.session.rollback(); flash(f'Error deleting: {e}', 'danger')
     return redirect(url_for('ingredients_list'))

# --- Recipe Management Routes ---
@app.route('/recipes')
def recipes_list():
    # ... (Keep existing code) ...
    recipes = Recipe.query.order_by(Recipe.name).all()
    return render_template('recipes_list.html', recipes=recipes)

@app.route('/recipes/add', methods=['GET', 'POST'])
def add_recipe():
    # ... (Keep existing code) ...
    form = RecipeForm()
    if form.validate_on_submit():
        try:
            new_recipe = Recipe(name=form.name.data.strip(),
                                description=form.description.data,
                                instructions=form.instructions.data,
                                meal_type_suitability=",".join(form.meal_type_suitability.data) or 'Any')
            db.session.add(new_recipe); db.session.commit()
            flash(f'Recipe "{new_recipe.name}" created.', 'success')
            return redirect(url_for('recipe_detail', recipe_id=new_recipe.id))
        except Exception as e:
            db.session.rollback(); flash(f'Error creating recipe: {e}', 'danger')
    return render_template('add_edit_recipe.html', form=form, title="Create New Recipe", action_url=url_for('add_recipe'))


@app.route('/recipes/<int:recipe_id>', methods=['GET'])
def recipe_detail(recipe_id):
    # Eager load relationships needed for display AND calculation check
    recipe = Recipe.query.options(
        db.selectinload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)
    ).get_or_404(recipe_id)
    add_ingredient_form = AddIngredientToRecipeForm()
    # Populate choices correctly
    current_ingredient_ids = {ri.ingredient_id for ri in recipe.ingredients}
    available = Ingredient.query.filter(Ingredient.id.notin_(current_ingredient_ids)).order_by(Ingredient.name).all()
    add_ingredient_form.ingredient_id.choices = [(i.id, f"{i.name} ({i.typical_unit})") for i in available]

    return render_template('recipe_detail.html', recipe=recipe, add_ingredient_form=add_ingredient_form)

@app.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    # ... (Keep existing code) ...
    recipe = Recipe.query.get_or_404(recipe_id)
    form = RecipeForm(obj=recipe)
    if request.method == 'GET':
        form.meal_type_suitability.data = recipe.meal_type_suitability.split(',') if recipe.meal_type_suitability else []
    if form.validate_on_submit():
        try:
            recipe.name = form.name.data.strip()
            recipe.description = form.description.data
            recipe.instructions = form.instructions.data
            recipe.meal_type_suitability = ",".join(form.meal_type_suitability.data) or 'Any'
            recipe.updated_at = datetime.utcnow()
            db.session.commit()
            flash(f'Recipe "{recipe.name}" updated.', 'success')
            return redirect(url_for('recipe_detail', recipe_id=recipe.id))
        except Exception as e:
            db.session.rollback(); flash(f'Error updating recipe: {e}', 'danger')
    return render_template('add_edit_recipe.html', form=form, title=f"Edit Recipe: {recipe.name}", action_url=url_for('edit_recipe', recipe_id=recipe_id))


@app.route('/recipes/<int:recipe_id>/add_ingredient', methods=['POST'])
def add_ingredient_to_recipe(recipe_id):
    # ... (Keep existing code with fixes: Use AddIngredientToRecipeForm, recalc/update totals) ...
    recipe = Recipe.query.get_or_404(recipe_id)
    form = AddIngredientToRecipeForm(request.form)
    # Repopulate choices for validation
    current_ingredient_ids = {ri.ingredient_id for ri in recipe.ingredients}
    available = Ingredient.query.filter(Ingredient.id.notin_(current_ingredient_ids)).order_by(Ingredient.name).all()
    form.ingredient_id.choices = [(i.id, f"{i.name} ({i.typical_unit})") for i in available]

    if form.validate_on_submit():
        ingredient = Ingredient.query.get(form.ingredient_id.data)
        if not ingredient: flash("Ingredient not found.", 'danger')
        else:
            try:
                # Add RI link
                new_ri = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id, quantity=form.quantity.data)
                db.session.add(new_ri)
                db.session.flush()
                # Expire and recalc
                db.session.expire(recipe)
                updated_totals = calculate_recipe_nutrition(recipe.id) # Use recipe.id
                if updated_totals:
                     recipe.total_calories = updated_totals['calories']
                     recipe.total_protein = updated_totals['protein']
                     recipe.total_carbs = updated_totals['carbs']
                     recipe.total_fat = updated_totals['fat']
                     recipe.total_fiber = updated_totals['fiber']
                     recipe.total_sugar = updated_totals['sugar']       # Added
                     recipe.total_calcium = updated_totals['calcium']     # Added
                     recipe.updated_at = datetime.utcnow()
                else: flash("Couldn't recalc recipe totals", "warning")
                db.session.commit()
                flash(f"Added {form.quantity.data} {ingredient.typical_unit} of {ingredient.name}.", 'success')
            except Exception as e:
                db.session.rollback(); flash(f"Error adding ingredient: {e}", 'danger')
                print(f"ERROR adding recipe ingredient {recipe.id}: {e}")
    else: # Validation failed
        error_messages = [f"{f.label.text}: {e}" for f, errs in form.errors.items() for e in errs]
        flash("Could not add ingredient: " + "; ".join(error_messages), "danger")

    return redirect(url_for('recipe_detail', recipe_id=recipe_id))


@app.route('/recipes/remove_ingredient/<int:recipe_ingredient_id>', methods=['POST'])
def remove_ingredient_from_recipe(recipe_ingredient_id):
    # ... (Keep existing code with fixes: Recalc/update totals after delete) ...
    ri = RecipeIngredient.query.options(db.joinedload(RecipeIngredient.ingredient)).get_or_404(recipe_ingredient_id)
    recipe_id = ri.recipe_id
    ingredient_name = ri.ingredient.name if ri.ingredient else '?'
    try:
        db.session.delete(ri)
        db.session.flush()
        # Expire and recalc
        recipe = Recipe.query.get(recipe_id)
        if recipe:
            db.session.expire(recipe)
            updated_totals = calculate_recipe_nutrition(recipe_id)
            if updated_totals:
                recipe.total_calories = updated_totals['calories']
                recipe.total_protein = updated_totals['protein']
                recipe.total_carbs = updated_totals['carbs']
                recipe.total_fat = updated_totals['fat']
                recipe.total_fiber = updated_totals['fiber']
                recipe.total_sugar = updated_totals['sugar']     # Added
                recipe.total_calcium = updated_totals['calcium']   # Added
                recipe.updated_at = datetime.utcnow()
            else: # Reset if empty or error
                recipe.total_calories = recipe.total_protein = recipe.total_carbs = None # etc.
                recipe.total_fat = recipe.total_fiber = recipe.total_sugar = recipe.total_calcium = None
                flash("Recipe totals reset.", "warning")

        db.session.commit()
        flash(f"Removed {ingredient_name} from recipe.", 'success')
    except Exception as e:
        db.session.rollback(); flash(f"Error removing ingredient: {e}", "danger")
        print(f"ERROR removing recipe ingredient {recipe_ingredient_id}: {e}")

    return redirect(url_for('recipe_detail', recipe_id=recipe_id))

@app.route('/recipes/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    # ... (Keep existing code) ...
    recipe = Recipe.query.get_or_404(recipe_id)
    try:
        db.session.delete(recipe) # Cascade handles RI links
        db.session.commit()
        flash(f'Recipe "{recipe.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Error deleting recipe: {e}', 'danger')
    return redirect(url_for('recipes_list'))

# --- Initialize Database ---
# Remove db.create_all() from here if using Flask-Migrate primarily
# Keep it if you want simple setup or might wipe DB often during dev
# with app.app_context():
#      print("Checking/creating database tables...")
#      try:
#          db.create_all()
#          print("Database tables checked/created.")
#      except Exception as e:
#          print(f"ERROR during db.create_all(): {e}")

# --- Run App (Local Development) ---
if __name__ == '__main__':
    # Ensure app context for operations like db access in form init
    with app.app_context():
        try:
             # Attempt a simple query to check DB connection early
             db.session.query(Food).first()
        except Exception as e:
             print("*"*20)
             print(f"WARNING: Initial DB check failed: {e}")
             print("Database might not exist or needs migration. Run 'flask db upgrade'.")
             print("*"*20)

    print("Starting Flask development server...")
    # Consider disabling debug/reloader temporarily if weird init errors persist
    # app.run(host='0.0.0.0', port=5000)
    app.run(debug=True, host='0.0.0.0', port=5000)