import os
from dotenv import load_dotenv # Import

# --- Load Environment Variables ---
load_dotenv() # Loads .env file variables FIRST

import requests # Import after dotenv potentially sets proxies etc.
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, SelectField, HiddenField, TextAreaField, SelectMultipleField
from wtforms.validators import DataRequired, NumberRange, InputRequired, Optional, Length, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput
import math
from flask_migrate import Migrate
from sqlalchemy import CheckConstraint, MetaData
from sqlalchemy.dialects.postgresql import JSONB # Import JSONB for PG
from sqlalchemy import JSON # Fallback JSON type

# --- App Configuration ---
app = Flask(__name__)

# --- Nutritionix API Configuration ---
NUTRITIONIX_API_URL_NATURAL = "https://trackapi.nutritionix.com/v2/natural/nutrients"
NUTRITIONIX_APP_ID = os.environ.get('NUTRITIONIX_APP_ID')
NUTRITIONIX_API_KEY = os.environ.get('NUTRITIONIX_API_KEY')

# --- Naming Convention (Essential for Alembic/Migrate) ---
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)

# Secret Key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-insecure-fallback-key')

# Database URI
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///' + os.path.join(basedir, 'local_tracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize DB and Migrate ---
db = SQLAlchemy(app, metadata=metadata) # Apply metadata
migrate = Migrate(app, db)

# --- Database Models ---

class Food(db.Model):
    __tablename__ = 'foods'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    base_unit = db.Column(db.String(50), nullable=False)
    base_quantity = db.Column(db.Float, nullable=False, default=100.0)
    calories = db.Column(db.Float, nullable=False, default=0)
    protein = db.Column(db.Float, nullable=False, default=0)
    carbs = db.Column(db.Float, nullable=False, default=0)
    fat = db.Column(db.Float, nullable=False, default=0)
    fiber = db.Column(db.Float, nullable=True, default=0.0) # Allow null, default 0
    sugar = db.Column(db.Float, nullable=True, default=0.0)
    calcium = db.Column(db.Float, nullable=True, default=0.0) 
    iron = db.Column(db.Float, nullable=True, default=0.0)      
    potassium = db.Column(db.Float, nullable=True, default=0.0) 
    sodium = db.Column(db.Float, nullable=True, default=0.0)    
    vit_d = db.Column(db.Float, nullable=True, default=0.0)    
    other_details = db.Column(db.JSON, nullable=True) # Flexible storage
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    logs = db.relationship('MealLog', backref='food', lazy='select', cascade="all, delete-orphan")
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
    sugar = db.Column(db.Float, nullable=True)
    calcium = db.Column(db.Float, nullable=True) 
    iron = db.Column(db.Float, nullable=True)      
    potassium = db.Column(db.Float, nullable=True) 
    sodium = db.Column(db.Float, nullable=True)    
    vit_d = db.Column(db.Float, nullable=True)     # Check API unit!
    other_details = db.Column(db.JSON, nullable=True) # Flexible storage
    data_source = db.Column(db.String(50), nullable=True) # 'manual', 'nutritionix'
    api_name = db.Column(db.String(250), nullable=True) # Name returned by API
    api_info = db.Column(db.String(100), nullable=True) # Original serving info
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recipes_where_used = db.relationship('RecipeIngredient', backref='ingredient', lazy='select')
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
    total_sugar = db.Column(db.Float, nullable=True)
    total_calcium = db.Column(db.Float, nullable=True)
    total_iron = db.Column(db.Float, nullable=True)
    total_potassium = db.Column(db.Float, nullable=True)
    total_sodium = db.Column(db.Float, nullable=True)
    total_vit_d = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ingredients = db.relationship('RecipeIngredient', backref='recipe', lazy='select', cascade='all, delete-orphan')
    logs = db.relationship('MealLog', backref='recipe', lazy='select')
    def __repr__(self): return f'<Recipe {self.name}>'

class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredients.id'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    # ingredient = defined by backref from Ingredient
    # recipe = defined by backref from Recipe
    def __repr__(self):
        ing_name = self.ingredient.name if hasattr(self, 'ingredient') and self.ingredient else '?'
        unit = self.ingredient.typical_unit if hasattr(self, 'ingredient') and self.ingredient else 'unit'
        rec_id = self.recipe.id if hasattr(self, 'recipe') and self.recipe else '?'
        return f'<{self.quantity} {unit} of {ing_name} in Recipe {rec_id}>'

class MealLog(db.Model):
    __tablename__ = 'meal_logs'
    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.Date, nullable=False, index=True)
    meal_type = db.Column(db.String(50), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey('foods.id'), nullable=True)
    recipe_id =db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True)
    quantity_consumed = db.Column(db.Float, nullable=False)
    calculated_calories = db.Column(db.Float, nullable=False)
    calculated_protein = db.Column(db.Float, nullable=False)
    calculated_carbs = db.Column(db.Float, nullable=False)
    calculated_fat = db.Column(db.Float, nullable=False)
    calculated_fiber = db.Column(db.Float, nullable=True)
    calculated_sugar = db.Column(db.Float, nullable=True)
    calculated_calcium = db.Column(db.Float, nullable=True)
    calculated_iron = db.Column(db.Float, nullable=True)
    calculated_potassium = db.Column(db.Float, nullable=True)
    calculated_sodium = db.Column(db.Float, nullable=True)
    calculated_vit_d = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # food defined by backref
    # recipe defined by backref
    __table_args__ = ( db.CheckConstraint('(food_id IS NOT NULL AND recipe_id IS NULL) OR (food_id IS NULL AND recipe_id IS NOT NULL)', name='meal_log_source_check'),)
    def __repr__(self): # Keep the adjusted repr
        if hasattr(self, 'food') and self.food:
            # ... repr for food ...
             return f'<MealLog Food ID {self.id}>' # Placeholder
        elif hasattr(self, 'recipe') and self.recipe:
            # ... repr for recipe ...
             return f'<MealLog Recipe ID {self.id}>' # Placeholder
        else: return f'<MealLog ID {self.id} - Invalid>'


# --- Forms ---

class IngredientForm(FlaskForm):
    name = StringField('Ingredient Name', validators=[DataRequired(), Length(max=150)])
    category = StringField('Category', validators=[Optional(), Length(max=100)], description="e.g., Vegetable, Protein")
    typical_unit = StringField('Typical Unit', default='g', validators=[DataRequired(), Length(max=50)], description="e.g., g, ml, piece")
    unit_quantity = FloatField('Nutrients Per Qty', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])
    calories = FloatField('Est. Calories', validators=[Optional(), NumberRange(min=0)])
    protein = FloatField('Est. Protein (g)', validators=[Optional(), NumberRange(min=0)])
    carbs = FloatField('Est. Carbs (g)', validators=[Optional(), NumberRange(min=0)])
    fat = FloatField('Est. Fat (g)', validators=[Optional(), NumberRange(min=0)])
    fiber = FloatField('Est. Fiber (g)', validators=[Optional(), NumberRange(min=0)])
    sugar = FloatField('Est. Sugar (g)', validators=[Optional(), NumberRange(min=0)])
    calcium = FloatField('Est. Calcium (mg)', validators=[Optional(), NumberRange(min=0)])
    iron = FloatField('Est. Iron (mg)', validators=[Optional(), NumberRange(min=0)])
    potassium = FloatField('Est. Potassium (mg)', validators=[Optional(), NumberRange(min=0)])
    sodium = FloatField('Est. Sodium (mg)', validators=[Optional(), NumberRange(min=0)])
    vit_d = FloatField('Est. Vit D (mcg)', validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('Notes', validators=[Optional()])
    data_source_flag = HiddenField(default='manual') # Tracks if data came from API lookup
    submit = SubmitField('Save Ingredient')

class FoodForm(FlaskForm):
    name = StringField('Food Name', validators=[DataRequired(), Length(max=150)])
    base_unit = StringField('Base Unit', validators=[DataRequired(), Length(max=50)])
    base_quantity = FloatField('Nutrients Per Qty', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])
    calories = FloatField('Calories (kcal)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    protein = FloatField('Protein (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    carbs = FloatField('Carbs (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fat = FloatField('Fat (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fiber = FloatField('Fiber (g)', default=0, validators=[Optional(), NumberRange(min=0)])
    sugar = FloatField('Sugar (g)', default=0, validators=[Optional(), NumberRange(min=0)])
    calcium = FloatField('Calcium (mg)', default=0, validators=[Optional(), NumberRange(min=0)])
    iron = FloatField('Iron (mg)', default=0, validators=[Optional(), NumberRange(min=0)])
    potassium = FloatField('Potassium (mg)', default=0, validators=[Optional(), NumberRange(min=0)])
    sodium = FloatField('Sodium (mg)', default=0, validators=[Optional(), NumberRange(min=0)])
    vit_d = FloatField('Vit D (mcg)', default=0, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Food')

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description (Optional)')
    instructions = TextAreaField('Instructions (Optional)')
    meal_type_suitability = SelectMultipleField('Suitable for Meals', choices=[('Breakfast','Breakfast'), ('Lunch','Lunch'), ('Dinner','Dinner'), ('Snack','Snack'), ('Any','Any')], option_widget=CheckboxInput(), widget=ListWidget(prefix_label=False), validators=[Optional()])
    submit = SubmitField('Save Recipe Details')

class AddIngredientToRecipeForm(FlaskForm):
    ingredient_id = SelectField('Ingredient', coerce=int, validators=[DataRequired()])
    quantity = FloatField('Quantity', validators=[InputRequired(), NumberRange(min=0.001)])
    submit = SubmitField('Add Ingredient')

class LogEntryForm(FlaskForm): # For logging FOOD items (manual db)
    food_id = SelectField('Food Item', coerce=int, validators=[DataRequired()])
    quantity_consumed = FloatField('Quantity Consumed', validators=[DataRequired(), NumberRange(min=0.001)])
    meal_type = HiddenField(validators=[DataRequired()])
    log_date = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Add to Log') # Name used to differentiate submits

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try: self.food_id.choices = [(f.id, f.name) for f in Food.query.order_by(Food.name).all()]
        except: self.food_id.choices = [] # Handle case where DB not ready

class LogRecipeForm(FlaskForm):
    recipe_id = SelectField('Recipe', coerce=int, validators=[DataRequired()])
    quantity_consumed = FloatField('Servings / Multiplier', default=1.0, validators=[InputRequired(), NumberRange(min=0.01)], description="e.g., 1=whole recipe, 0.5=half")
    meal_type = HiddenField(validators=[DataRequired()])
    log_date = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Log Recipe') # Name used to differentiate submits

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try: self.recipe_id.choices = [(r.id, r.name) for r in Recipe.query.order_by(Recipe.name).all()]
        except: self.recipe_id.choices = [] # Handle case where DB not ready

# --- Helper Functions ---

def get_nutritionix_ingredient_data(ingredient_name):
    """ Queries Nutritionix API, returns dict with data ready for DB/Form or None """
    if not NUTRITIONIX_APP_ID or not NUTRITIONIX_API_KEY:
        print("ERROR: Nutritionix API credentials missing.")
        flash("API credentials not configured. Cannot lookup.", "error")
        return None

    query = f"100g {ingredient_name}" # Try getting per 100g directly
    headers = {'x-app-id': NUTRITIONIX_APP_ID, 'x-app-key': NUTRITIONIX_API_KEY, 'Content-Type':'application/json'}
    payload = {"query": query}
    print(f"DEBUG: Querying Nutritionix: {query}")

    try:
        response = requests.post(NUTRITIONIX_API_URL_NATURAL, headers=headers, json=payload, timeout=15)
        print(f"DEBUG: API Status Code: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        # import json; print(f"DEBUG: Raw API data: {json.dumps(data, indent=2)}") # Uncomment for deep debug

        if data and 'foods' in data and data['foods']:
            food_data = data['foods'][0]
            parsed = { # Store raw API values first
                'name': food_data.get('food_name'),
                'api_serving_qty': food_data.get('serving_qty'),
                'api_serving_unit': food_data.get('serving_unit'),
                'api_serving_grams': food_data.get('serving_weight_grams'),
                'calories': food_data.get('nf_calories'),
                'protein': food_data.get('nf_protein'),
                'carbs': food_data.get('nf_total_carbohydrate'),
                'fat': food_data.get('nf_total_fat'),
                'fiber': food_data.get('nf_dietary_fiber'),
                'sugar': food_data.get('nf_sugars'),
                'calcium': food_data.get('nf_calcium_mg'), # Assume mg
                'iron': food_data.get('nf_iron_mg'),      # Assume mg
                'potassium': food_data.get('nf_potassium'),  # Assume mg
                'sodium': food_data.get('nf_sodium'),      # Assume mg
                'vit_d': food_data.get('nf_vitamin_d_mcg'),# Assume mcg
                'nix_id': food_data.get('nix_item_id') or food_data.get('tag_id'),
                'photo': food_data.get('photo', {}).get('thumb'),
            }

            # Collect OTHER nf_ fields into a dictionary
            other_nutrients_dict = {}
            exclude_keys = ['nf_calories', 'nf_protein', 'nf_total_carbohydrate', 'nf_total_fat', 'nf_dietary_fiber',
                            'nf_sugars', 'nf_calcium_mg', 'nf_iron_mg', 'nf_potassium', 'nf_sodium', 'nf_vitamin_d_mcg',
                            'nf_cholesterol'] # Add others to EXCLUDE from JSON here if needed
            for key, value in food_data.items():
                if key.startswith('nf_') and key not in exclude_keys:
                     if value is not None: other_nutrients_dict[key.replace('nf_','')] = value # Store cleaned key name
            # Add specific non-nf fields if desired (e.g. cholesterol)
            cholesterol = food_data.get('nf_cholesterol')
            if cholesterol is not None: other_nutrients_dict['cholesterol'] = cholesterol

            # --- Normalize to DB format (usually per 100g) ---
            grams = parsed.get('api_serving_grams')
            db_data = {'source': 'nutritionix', 'other_details': other_nutrients_dict or None}
            factor = 1.0

            if grams and grams > 0 and abs(grams - 100.0) > 1:
                print(f"WARN: Normalizing API data from {grams:.1f}g to 100g for {ingredient_name}")
                factor = 100.0 / grams
                db_data['base_unit'] = 'g'; db_data['unit_quantity'] = 100.0
            elif grams and abs(grams - 100.0) <= 1:
                 db_data['base_unit'] = 'g'; db_data['unit_quantity'] = 100.0; factor = 1.0
            else: # Cannot normalize, use API serving
                 print(f"WARN: Storing {ingredient_name} as per API serving: {parsed.get('api_serving_qty')} {parsed.get('api_serving_unit')}")
                 db_data['base_unit'] = parsed.get('api_serving_unit', 'serving'); db_data['unit_quantity'] = parsed.get('api_serving_qty', 1.0); factor = 1.0

            def safe_mult(v, f): return (float(v) * f) if v is not None else None
            db_data['calories'] = safe_mult(parsed.get('calories'), factor)
            db_data['protein'] = safe_mult(parsed.get('protein'), factor)
            db_data['carbs'] = safe_mult(parsed.get('carbs'), factor)
            db_data['fat'] = safe_mult(parsed.get('fat'), factor)
            db_data['fiber'] = safe_mult(parsed.get('fiber'), factor)
            db_data['sugar'] = safe_mult(parsed.get('sugar'), factor)
            db_data['calcium'] = safe_mult(parsed.get('calcium'), factor)
            db_data['iron'] = safe_mult(parsed.get('iron'), factor)
            db_data['potassium'] = safe_mult(parsed.get('potassium'), factor)
            db_data['sodium'] = safe_mult(parsed.get('sodium'), factor)
            db_data['vit_d'] = safe_mult(parsed.get('vit_d'), factor)

            db_data['name_from_api'] = parsed.get('name')
            serving_info_grams = f" ({grams:.1f}g)" if grams is not None else ""
            db_data['api_info_str'] = f"API: {parsed.get('api_serving_qty')} {parsed.get('api_serving_unit', '')}{serving_info_grams}".strip()

            print(f"DEBUG: Returning db_data: {db_data}")
            return db_data

        else: print(f"No 'foods' in Nutritionix response for '{ingredient_name}'"); return None
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: Nutritionix HTTP Error {e.response.status_code} for '{query}'. Body: {e.response.text[:500]}")
        if e.response.status_code == 404: flash(f"'{ingredient_name}' not found by Nutritionix.", 'warning')
        else: flash("Nutritionix API Error (check keys/status).", "danger")
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Nutritionix Connection Error: {e}"); flash("Network error reaching Nutritionix.", "error"); return None
    except Exception as e:
        print(f"ERROR: Processing Nutritionix data failed: {e}"); import traceback; traceback.print_exc(); flash("Error processing API data.", "error"); return None


def calculate_recipe_nutrition(recipe_id):
    """ Calculates and returns total estimated nutrition for a given recipe ID. """
    totals = {'calories':0.0, 'protein':0.0, 'carbs':0.0, 'fat':0.0, 'fiber':0.0, 'sugar':0.0, 'calcium':0.0, 'iron':0.0, 'potassium':0.0, 'sodium':0.0, 'vit_d':0.0}
    recipe = Recipe.query.get(recipe_id)
    if not recipe: return None

    recipe_ingredients = recipe.ingredients # Use direct relationship (list)

    for ri in recipe_ingredients:
        ingredient = ri.ingredient # Use relationship attribute
        if not ingredient: continue # Skip if link broken

        qty_used = ri.quantity
        unit_qty = ingredient.unit_quantity

        if unit_qty is None or unit_qty == 0: continue # Skip if base qty is invalid

        try: multiplier = float(qty_used) / float(unit_qty)
        except: continue # Skip if calculation fails

        def safe_get(v): return float(v) if v is not None else 0.0

        totals['calories'] += (safe_get(ingredient.calories) * multiplier)
        totals['protein']  += (safe_get(ingredient.protein) * multiplier)
        totals['carbs']    += (safe_get(ingredient.carbs) * multiplier)
        totals['fat']      += (safe_get(ingredient.fat) * multiplier)
        totals['fiber']    += (safe_get(ingredient.fiber) * multiplier)
        totals['sugar']    += (safe_get(ingredient.sugar) * multiplier)
        totals['calcium']  += (safe_get(ingredient.calcium) * multiplier)
        totals['iron']     += (safe_get(ingredient.iron) * multiplier)
        totals['potassium']+= (safe_get(ingredient.potassium) * multiplier)
        totals['sodium']   += (safe_get(ingredient.sodium) * multiplier)
        totals['vit_d']    += (safe_get(ingredient.vit_d) * multiplier)

    for key in totals: # Ensure finite
        if not isinstance(totals[key],(int,float)) or not math.isfinite(totals[key]): totals[key]=0.0

    return totals

def calculate_nutrients(food, quantity_consumed):
    """ Calculates nutrients for a specific food log entry. """
    results = {'calories':0.0, 'protein':0.0, 'carbs':0.0, 'fat':0.0, 'fiber':0.0, 'sugar':0.0, 'calcium':0.0, 'iron':0.0, 'potassium':0.0, 'sodium':0.0, 'vit_d':0.0}
    if not food or food.base_quantity is None or food.base_quantity == 0 or quantity_consumed is None: return results

    try:
        multiplier = float(quantity_consumed) / float(food.base_quantity)
        def safe_calc(v, m):
             if v is None: return 0.0
             try: r = float(v)*m; return r if math.isfinite(r) else 0.0
             except: return 0.0

        results['calories'] = safe_calc(food.calories, multiplier)
        results['protein']  = safe_calc(food.protein, multiplier)
        results['carbs']    = safe_calc(food.carbs, multiplier)
        results['fat']      = safe_calc(food.fat, multiplier)
        results['fiber']    = safe_calc(food.fiber, multiplier)
        results['sugar']    = safe_calc(food.sugar, multiplier)
        results['calcium']  = safe_calc(food.calcium, multiplier)
        results['iron']     = safe_calc(food.iron, multiplier)
        results['potassium'] = safe_calc(food.potassium, multiplier)
        results['sodium']   = safe_calc(food.sodium, multiplier)
        results['vit_d']    = safe_calc(food.vit_d, multiplier)

    except Exception as e: print(f"WARN: Error calculating nutrients: {e}")
    return results

def get_day_summary(log_date_obj):
    """ Calculates total nutrients for a given date. """
    logs = MealLog.query.filter_by(log_date=log_date_obj).options(db.joinedload(MealLog.food), db.joinedload(MealLog.recipe)).all()
    summary = {'calories':0, 'protein':0, 'carbs':0, 'fat':0, 'fiber':0, 'sugar':0, 'calcium':0, 'iron':0, 'potassium':0, 'sodium':0, 'vit_d':0}
    for log in logs:
        summary['calories'] += log.calculated_calories or 0
        summary['protein'] += log.calculated_protein or 0
        summary['carbs'] += log.calculated_carbs or 0
        summary['fat'] += log.calculated_fat or 0
        summary['fiber'] += log.calculated_fiber or 0
        summary['sugar'] += log.calculated_sugar or 0
        summary['calcium'] += log.calculated_calcium or 0
        summary['iron'] += log.calculated_iron or 0
        summary['potassium'] += log.calculated_potassium or 0
        summary['sodium'] += log.calculated_sodium or 0
        summary['vit_d'] += log.calculated_vit_d or 0
    return summary

# --- Routes ---

@app.route('/', methods=['GET'])
def index(): return redirect(url_for('daily_log', date=date.today().isoformat()))

@app.route('/log', methods=['GET'])
def daily_log():
    # ... (GET logic remains the same, fetching logs/summary, instantiating forms) ...
    log_date_str = request.args.get('date', date.today().isoformat())
    try: log_date_obj = date.fromisoformat(log_date_str)
    except ValueError: log_date_obj = date.today(); log_date_str = log_date_obj.isoformat(); flash('Invalid date.', 'warning')
    log_food_form = LogEntryForm(log_date=log_date_str)
    log_recipe_form = LogRecipeForm(log_date=log_date_str)
    logs_by_meal = {}
    meal_types = ['Breakfast', 'Lunch', 'Dinner', 'Snacks']
    for meal in meal_types:
        logs_by_meal[meal] = MealLog.query.filter_by(log_date=log_date_obj, meal_type=meal).order_by(MealLog.created_at).options(db.joinedload(MealLog.food), db.joinedload(MealLog.recipe)).all()
    daily_summary = get_day_summary(log_date_obj)
    prev_date = (log_date_obj - timedelta(days=1)).isoformat()
    next_date = (log_date_obj + timedelta(days=1)).isoformat()
    return render_template('daily_log.html', log_form=log_food_form, log_recipe_form=log_recipe_form, current_date_str=log_date_str, current_date_obj=log_date_obj, prev_date=prev_date, next_date=next_date, logs_by_meal=logs_by_meal, daily_summary=daily_summary, meal_types=meal_types)

@app.route('/log/food', methods=['POST'])
def log_food_entry():
    # ... (Keep this route using manual Food DB as per starting point) ...
    form = LogEntryForm(request.form)
    log_date_str = form.log_date.data or date.today().isoformat()
    if not form.food_id.choices: form.food_id.choices = [(f.id, f.name) for f in Food.query.order_by(Food.name).all()]

    if form.validate_on_submit():
        try:
            food = Food.query.get_or_404(form.food_id.data)
            quantity = form.quantity_consumed.data
            calculated = calculate_nutrients(food, quantity)
            new_log = MealLog(log_date=date.fromisoformat(log_date_str), meal_type=form.meal_type.data, food_id=food.id, recipe_id=None, quantity_consumed=quantity, **{f'calculated_{k}': v for k, v in calculated.items()})
            db.session.add(new_log); db.session.commit()
            flash(f'Added {quantity} {food.base_unit} of {food.name}.', 'success')
        except Exception as e: db.session.rollback(); flash(f'Error logging food: {e}', 'danger'); print(f"ERROR log food: {e}")
    else: flash("Log food error: " + "; ".join([f"{f.label.text}: {e}" for f,errs in form.errors.items() for e in errs]), "danger")
    return redirect(url_for('daily_log', date=log_date_str))

@app.route('/log/recipe', methods=['POST'])
def log_recipe_entry():
    # ... (Keep existing code, ensure it saves new calculated nutrients) ...
    form = LogRecipeForm(request.form)
    log_date_str = form.log_date.data or date.today().isoformat()
    if not form.recipe_id.choices: form.recipe_id.choices = [(r.id, r.name) for r in Recipe.query.order_by(Recipe.name).all()]

    if form.validate_on_submit():
        try:
            recipe = Recipe.query.get_or_404(form.recipe_id.data)
            quantity = form.quantity_consumed.data # Multiplier
            # Calculate portion nutrients
            nutrients = {f"calculated_{key.replace('total_','')}": (getattr(recipe, key) or 0.0) * quantity for key in recipe.__table__.columns.keys() if key.startswith('total_')}

            new_log = MealLog(log_date=date.fromisoformat(log_date_str), meal_type=form.meal_type.data, recipe_id=recipe.id, food_id=None, quantity_consumed=quantity, **nutrients)
            db.session.add(new_log); db.session.commit()
            serv_str = f'{quantity} {"serving" if quantity == 1 else "servings"}'; flash(f'Logged {serv_str} of "{recipe.name}".', 'success')
        except Exception as e: db.session.rollback(); flash(f'Error logging recipe: {e}', 'danger'); print(f"ERROR log recipe: {e}")
    else: flash("Log recipe error: " + "; ".join([f"{f.label.text}: {e}" for f,errs in form.errors.items() for e in errs]), "danger")
    return redirect(url_for('daily_log', date=log_date_str))


@app.route('/log/delete/<int:log_id>', methods=['POST'])
def delete_log_entry(log_id):
    # ... (Keep existing code) ...
    log = MealLog.query.get_or_404(log_id)
    date_str = log.log_date.isoformat()
    try: db.session.delete(log); db.session.commit(); flash("Log entry deleted.", "success")
    except Exception as e: db.session.rollback(); flash(f"Error deleting log: {e}", "danger")
    return redirect(url_for('daily_log', date=date_str))

# --- Food Database Routes (Manual) ---
@app.route('/database')
def database_view():
    foods = Food.query.order_by(Food.name).all()
    return render_template('database_view.html', foods=foods)

@app.route('/database/add', methods=['GET', 'POST'])
def add_food():
    form = FoodForm()
    if form.validate_on_submit():
        if Food.query.filter(db.func.lower(Food.name) == form.name.data.strip().lower()).first(): flash('Name exists.', 'danger')
        else:
            try:
                new_food = Food( # Ensure all fields (incl. new micros) are assigned
                     name=form.name.data.strip(), base_unit=form.base_unit.data.strip(), base_quantity=form.base_quantity.data,
                     calories=form.calories.data, protein=form.protein.data, carbs=form.carbs.data, fat=form.fat.data,
                     fiber=form.fiber.data, sugar=form.sugar.data, calcium=form.calcium.data, iron=form.iron.data,
                     potassium=form.potassium.data, sodium=form.sodium.data, vit_d=form.vit_d.data, notes=form.notes.data
                )
                db.session.add(new_food); db.session.commit(); flash(f'"{new_food.name}" added.', 'success'); return redirect(url_for('database_view'))
            except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('add_edit_food.html', form=form, title='Add Food', action_url=url_for('add_food'))

@app.route('/database/edit/<int:food_id>', methods=['GET', 'POST'])
def edit_food(food_id):
    food = Food.query.get_or_404(food_id)
    form = FoodForm(obj=food)
    if form.validate_on_submit():
         if Food.query.filter(db.func.lower(Food.name) == form.name.data.strip().lower(), Food.id != food_id).first(): flash('Name exists.', 'danger')
         else:
            try: # Assign ALL fields from form
                 food.name=form.name.data.strip(); food.base_unit=form.base_unit.data.strip(); food.base_quantity=form.base_quantity.data
                 food.calories=form.calories.data; food.protein=form.protein.data; food.carbs=form.carbs.data; food.fat=form.fat.data
                 food.fiber=form.fiber.data; food.sugar=form.sugar.data; food.calcium=form.calcium.data; food.iron=form.iron.data
                 food.potassium=form.potassium.data; food.sodium=form.sodium.data; food.vit_d=form.vit_d.data; food.notes=form.notes.data
                 food.updated_at = datetime.utcnow()
                 db.session.commit(); flash(f'"{food.name}" updated.', 'success'); return redirect(url_for('database_view'))
            except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('add_edit_food.html', form=form, title=f'Edit: {food.name}', action_url=url_for('edit_food', food_id=food_id))

@app.route('/database/delete/<int:food_id>', methods=['POST'])
def delete_food(food_id):
    # ... (Keep existing code) ...
    food = Food.query.get_or_404(food_id)
    try: db.session.delete(food); db.session.commit(); flash(f'"{food.name}" deleted.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return redirect(url_for('database_view'))

# --- Ingredient Routes ---
@app.route('/ingredients')
def ingredients_list():
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    return render_template('ingredients_list.html', ingredients=ingredients)

@app.route('/ingredients/add', methods=['GET', 'POST'])
def add_ingredient():
    form = IngredientForm()
    lookup_name = request.args.get('lookup_name')

    if request.method == 'GET' and lookup_name:
        api_data = get_nutritionix_ingredient_data(lookup_name)
        if api_data:
            form = IngredientForm(data=api_data) # Pre-populate directly if keys match form field names
            form.name.data = lookup_name # Use original search name
            form.notes.data = api_data.get('api_info_str','') # Use API info for notes
            form.data_source_flag.data = 'nutritionix' # Set flag
            flash(f"Review data found for '{lookup_name}'.", 'info')
        else:
            form.name.data = lookup_name; flash(f"No data found for '{lookup_name}'. Enter manually.", 'warning')

    if form.validate_on_submit(): # POST logic
        if Ingredient.query.filter(db.func.lower(Ingredient.name) == form.name.data.strip().lower()).first():
            flash('Ingredient name exists.', 'danger')
        else:
            try:
                data_source = form.data_source_flag.data or 'manual'
                new_ingredient = Ingredient( # Assign all fields incl new micros, api fields, json
                    name=form.name.data.strip(), category=form.category.data.strip() or None,
                    typical_unit=form.typical_unit.data.strip(), unit_quantity=form.unit_quantity.data,
                    calories=form.calories.data, protein=form.protein.data, carbs=form.carbs.data,
                    fat=form.fat.data, fiber=form.fiber.data, sugar=form.sugar.data, calcium=form.calcium.data,
                    iron=form.iron.data, potassium=form.potassium.data, sodium=form.sodium.data, vit_d=form.vit_d.data,
                    notes=form.notes.data, # Save user notes
                    data_source=data_source,
                    api_info=form.notes.data if data_source == 'nutritionix' else None, # Example: If API source, store notes content as API info
                    api_name=form.name.data if data_source == 'nutritionix' else None, # Example: If API source, store form name as API name
                    other_details=api_data.get('other_details') if request.method=='GET' and lookup_name and api_data and data_source=='nutritionix' else None # Get from initial GET if API call was made
                    # Note: Need a better way to pass 'other_details' from GET to POST if using hidden field isn't ideal
                )
                db.session.add(new_ingredient); db.session.commit()
                flash(f'Ingredient "{new_ingredient.name}" ({data_source}) added.', 'success')
                return redirect(url_for('ingredients_list'))
            except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger'); print(f"ERROR add ingredient: {e}")

    return render_template('add_edit_ingredient.html', form=form, title='Add Ingredient', action_url=url_for('add_ingredient'))


@app.route('/ingredients/edit/<int:ingredient_id>', methods=['GET', 'POST'])
def edit_ingredient(ingredient_id):
    # ... (Keep existing logic, ensure ALL new fields are handled on POST) ...
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    form = IngredientForm(obj=ingredient)
    if form.validate_on_submit():
        if Ingredient.query.filter(db.func.lower(Ingredient.name) == form.name.data.strip().lower(), Ingredient.id != ingredient_id).first(): flash('Name exists.', 'danger')
        else:
            try: # Assign all fields
                 ingredient.name = form.name.data.strip(); ingredient.category = form.category.data.strip() or None
                 ingredient.typical_unit = form.typical_unit.data.strip(); ingredient.unit_quantity = form.unit_quantity.data
                 ingredient.calories = form.calories.data; ingredient.protein = form.protein.data; ingredient.carbs = form.carbs.data
                 ingredient.fat = form.fat.data; ingredient.fiber = form.fiber.data; ingredient.sugar = form.sugar.data
                 ingredient.calcium = form.calcium.data; ingredient.iron = form.iron.data; ingredient.potassium = form.potassium.data
                 ingredient.sodium = form.sodium.data; ingredient.vit_d = form.vit_d.data; ingredient.notes = form.notes.data
                 # Decide if editing should reset data_source? For now, let's not.
                 ingredient.updated_at = datetime.utcnow()
                 db.session.commit(); flash(f'Ingredient "{ingredient.name}" updated.', 'success'); return redirect(url_for('ingredients_list'))
            except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('add_edit_ingredient.html', form=form, title=f'Edit: {ingredient.name}', action_url=url_for('edit_ingredient', ingredient_id=ingredient_id))


@app.route('/ingredients/delete/<int:ingredient_id>', methods=['POST'])
def delete_ingredient(ingredient_id):
    # ... (Keep existing code) ...
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    try: db.session.delete(ingredient); db.session.commit(); flash(f'"{ingredient.name}" deleted.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return redirect(url_for('ingredients_list'))

# --- Recipe Routes ---
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
            new_recipe = Recipe(name=form.name.data.strip(), description=form.description.data, instructions=form.instructions.data, meal_type_suitability=",".join(form.meal_type_suitability.data) or 'Any')
            db.session.add(new_recipe); db.session.commit()
            flash(f'Recipe "{new_recipe.name}" created.', 'success')
            return redirect(url_for('recipe_detail', recipe_id=new_recipe.id))
        except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('add_edit_recipe.html', form=form, title="Create Recipe", action_url=url_for('add_recipe'))

@app.route('/recipes/<int:recipe_id>', methods=['GET'])
def recipe_detail(recipe_id):
    # ... (Keep existing code) ...
    recipe = Recipe.query.options(db.selectinload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)).get_or_404(recipe_id)
    add_ingredient_form = AddIngredientToRecipeForm()
    current_ids = {ri.ingredient_id for ri in recipe.ingredients}; available = Ingredient.query.filter(Ingredient.id.notin_(current_ids)).order_by(Ingredient.name).all()
    add_ingredient_form.ingredient_id.choices = [(i.id, f"{i.name} ({i.typical_unit})") for i in available]
    return render_template('recipe_detail.html', recipe=recipe, add_ingredient_form=add_ingredient_form)


@app.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    # ... (Keep existing code) ...
    recipe = Recipe.query.get_or_404(recipe_id); form = RecipeForm(obj=recipe)
    if request.method == 'GET': form.meal_type_suitability.data = recipe.meal_type_suitability.split(',') if recipe.meal_type_suitability else []
    if form.validate_on_submit():
        try:
             recipe.name=form.name.data.strip(); recipe.description=form.description.data; recipe.instructions=form.instructions.data
             recipe.meal_type_suitability = ",".join(form.meal_type_suitability.data) or 'Any'; recipe.updated_at = datetime.utcnow()
             db.session.commit(); flash(f'"{recipe.name}" updated.', 'success'); return redirect(url_for('recipe_detail', recipe_id=recipe.id))
        except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return render_template('add_edit_recipe.html', form=form, title=f"Edit: {recipe.name}", action_url=url_for('edit_recipe', recipe_id=recipe_id))


@app.route('/recipes/<int:recipe_id>/add_ingredient', methods=['POST'])
def add_ingredient_to_recipe(recipe_id):
    # ... (Keep existing code - ensure ALL totals are updated) ...
    recipe = Recipe.query.get_or_404(recipe_id); form = AddIngredientToRecipeForm(request.form)
    current_ids = {ri.ingredient_id for ri in recipe.ingredients}; available = Ingredient.query.filter(Ingredient.id.notin_(current_ids)).order_by(Ingredient.name).all()
    form.ingredient_id.choices = [(i.id, f"{i.name} ({i.typical_unit})") for i in available]
    if form.validate_on_submit():
        ingredient = Ingredient.query.get(form.ingredient_id.data)
        if not ingredient: flash("Ingredient not found.",'danger')
        elif RecipeIngredient.query.filter_by(recipe_id=recipe.id, ingredient_id=ingredient.id).first(): flash(f"{ingredient.name} already in recipe.", 'warning')
        else:
            try:
                new_ri = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id, quantity=form.quantity.data); db.session.add(new_ri); db.session.flush()
                db.session.expire(recipe) # Force reload before calculation
                updated_totals = calculate_recipe_nutrition(recipe.id)
                if updated_totals:
                     recipe.total_calories = updated_totals['calories']; recipe.total_protein = updated_totals['protein']; recipe.total_carbs = updated_totals['carbs']
                     recipe.total_fat = updated_totals['fat']; recipe.total_fiber = updated_totals['fiber']; recipe.total_sugar = updated_totals['sugar']
                     recipe.total_calcium = updated_totals['calcium']; recipe.total_iron = updated_totals['iron']; recipe.total_potassium = updated_totals['potassium']
                     recipe.total_sodium = updated_totals['sodium']; recipe.total_vit_d = updated_totals['vit_d']
                     recipe.updated_at = datetime.utcnow()
                else: flash("Couldn't recalc totals", "warning")
                db.session.commit(); flash(f"Added {form.quantity.data} {ingredient.typical_unit} of {ingredient.name}.", 'success')
            except Exception as e: db.session.rollback(); flash(f"Error: {e}", 'danger'); print(f"ERROR add RI {recipe.id}: {e}")
    else: flash("Add ingredient error: " + "; ".join([f"{f.label.text}: {e}" for f,errs in form.errors.items() for e in errs]), "danger")
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))


@app.route('/recipes/remove_ingredient/<int:recipe_ingredient_id>', methods=['POST'])
def remove_ingredient_from_recipe(recipe_ingredient_id):
    # ... (Keep existing code - ensure ALL totals are updated/reset) ...
    ri = RecipeIngredient.query.options(db.joinedload(RecipeIngredient.ingredient)).get_or_404(recipe_ingredient_id)
    recipe_id = ri.recipe_id; ingredient_name = ri.ingredient.name if ri.ingredient else '?'
    try:
        db.session.delete(ri); db.session.flush()
        recipe = Recipe.query.get(recipe_id)
        if recipe:
            db.session.expire(recipe)
            updated_totals = calculate_recipe_nutrition(recipe_id)
            if updated_totals:
                 recipe.total_calories=updated_totals['calories']; recipe.total_protein=updated_totals['protein']; recipe.total_carbs=updated_totals['carbs']
                 recipe.total_fat=updated_totals['fat']; recipe.total_fiber=updated_totals['fiber']; recipe.total_sugar=updated_totals['sugar']
                 recipe.total_calcium=updated_totals['calcium']; recipe.total_iron=updated_totals['iron']; recipe.total_potassium=updated_totals['potassium']
                 recipe.total_sodium=updated_totals['sodium']; recipe.total_vit_d=updated_totals['vit_d']
                 recipe.updated_at = datetime.utcnow()
            else: # Reset totals if recipe empty or calc fails
                 recipe.total_calories = recipe.total_protein = recipe.total_carbs = recipe.total_fat = None
                 recipe.total_fiber = recipe.total_sugar = recipe.total_calcium = recipe.total_iron = None
                 recipe.total_potassium = recipe.total_sodium = recipe.total_vit_d = None
                 flash("Recipe totals reset.", "warning")
        db.session.commit(); flash(f"Removed {ingredient_name}.", 'success')
    except Exception as e: db.session.rollback(); flash(f"Error: {e}", "danger"); print(f"ERROR remove RI {recipe_ingredient_id}: {e}")
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))


@app.route('/recipes/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    # ... (Keep existing code) ...
    recipe = Recipe.query.get_or_404(recipe_id)
    try: db.session.delete(recipe); db.session.commit(); flash(f'"{recipe.name}" deleted.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Error: {e}', 'danger')
    return redirect(url_for('recipes_list'))

# --- Initialize Database / Migrations ---
# Comment out db.create_all() if using Flask-Migrate exclusively after first run
# with app.app_context(): db.create_all()

# --- Run App ---
if __name__ == '__main__':
    # Context needed? Maybe not here, but doesn't hurt for potential extensions
    with app.app_context():
        pass # Placeholder if startup checks removed
    app.run(debug=True, host='0.0.0.0', port=5000)