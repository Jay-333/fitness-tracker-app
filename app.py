import os
import requests
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, SelectField, HiddenField, TextAreaField, SelectMultipleField
from wtforms.validators import DataRequired, NumberRange, InputRequired, Optional, Length
from wtforms.widgets import ListWidget, CheckboxInput
import math
from flask_migrate import Migrate

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
migrate = Migrate(app, db)

# --- Database Models ---
# NEW: Model for Recipes/Meal Components
class Recipe(db.Model):
    __tablename__ = 'recipes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    # Suitability for meal types (could store as comma-separated string or use a separate relationship later)
    meal_type_suitability = db.Column(db.String(100), nullable=True, default='Any')

    # Calculated nutrition per serving (we'll define 'serving' implicitly for now or add a field later)
    # Store calculated values to avoid re-calculating every time
    total_calories = db.Column(db.Float, nullable=True)
    total_protein = db.Column(db.Float, nullable=True)
    total_carbs = db.Column(db.Float, nullable=True)
    total_fat = db.Column(db.Float, nullable=True)
    total_fiber = db.Column(db.Float, nullable=True)
    total_sugar = db.Column(db.Float, nullable=True)
    total_calcium = db.Column(db.Float, nullable=True)
    # Add others...

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to the ingredients used in this recipe
    # cascade='all, delete-orphan' means if a Recipe is deleted, its RecipeIngredient entries are also deleted.
    ingredients = db.relationship('RecipeIngredient', backref='recipe', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Recipe {self.name}>'


# NEW: Association table/model to link Recipes and Ingredients with quantities
class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True) # Simple primary key for the link itself
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredients.id'), nullable=False, index=True)

    # Quantity of the ingredient used IN THE UNIT defined in the Ingredient model's 'typical_unit'
    # e.g., 150 (if Ingredient.typical_unit is 'g'), 2 (if Ingredient.typical_unit is 'piece'), 0.5 (if 'cup')
    quantity = db.Column(db.Float, nullable=False)

    # Establish relationships for easy access (optional but convenient)
    ingredient = db.relationship('Ingredient', backref='recipe_assoc') # Allows easy access recipe_ingredient.ingredient.name etc.

    def __repr__(self):
        ing_name = self.ingredient.name if self.ingredient else 'Unknown Ingredient'
        unit = self.ingredient.typical_unit if self.ingredient else 'unit'
        return f'<RecipeIngredient {self.quantity} {unit} of {ing_name} for Recipe ID {self.recipe_id}>'


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
    sugar = db.Column(db.Float, nullable=True, default=0)
    calcium = db.Column(db.Float, nullable=True, default=0)
    # Add other macros/micros as needed (e.g., sugar, sodium)
    notes = db.Column(db.Text, nullable=True) # Optional notes field

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to log entries
    logs = db.relationship('MealLog', backref='food', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Food {self.name}>'



class Ingredient(db.Model):
    __tablename__ = 'ingredients' # Table for base ingredients
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    category = db.Column(db.String(100), nullable=True) # e.g., Vegetable, Fruit, Protein...
    # Typical unit used when adding this ingredient to a recipe
    typical_unit = db.Column(db.String(50), nullable=False, default='g') # e.g., g, ml, piece, cup

    # --- Estimated Nutrition Fields ---
    # Quantity of 'typical_unit' these nutrients refer to (e.g., 100 for 100g, 1 for 1 piece)
    unit_quantity = db.Column(db.Float, nullable=False, default=100.0)
    # Nutritional values PER 'unit_quantity' of 'typical_unit' - Allow NULL if unknown
    calories = db.Column(db.Float, nullable=True)
    protein = db.Column(db.Float, nullable=True)
    carbs = db.Column(db.Float, nullable=True)
    fat = db.Column(db.Float, nullable=True)
    fiber = db.Column(db.Float, nullable=True)
    sugar = db.Column(db.Float, nullable=True)
    calcium = db.Column(db.Float, nullable=True)
    # Add other fields like sugar, sodium if desired

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipe_links = db.relationship('RecipeIngredient', backref='ingredient_detail', lazy='dynamic') #Added lazy dynamic

    def __repr__(self):
        return f'<Ingredient {self.name}>'

# ... Keep other existing models (Food, MealLog) ...


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
    calculated_sugar = db.Column(db.Float, nullable=True)
    calculated_calcium = db.Column(db.Float, nullable=True)
    # Add other calculated fields matching Food model

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        food_name = self.food.name if self.food else 'Recipe unknown'
        unit = self.food.base_unit if self.food else 'serving'
        return f'<MealLog {self.quantity_consumed} {unit} of {food_name} on {self.log_date}>'

# --- Forms ---

# Form for basic Recipe Details
class AddIngredientToRecipeForm(FlaskForm):
    # Choices populated dynamically in the route
    ingredient_id = SelectField('Ingredient', coerce=int, validators=[DataRequired()])
    quantity = FloatField('Quantity', validators=[InputRequired(), NumberRange(min=0.001)])
    submit = SubmitField('Add Ingredient')

    # Optional: Override __init__ if complex dynamic choices needed,
    # but often easier to set choices in the route handler.
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.ingredient_id.choices = [] # Start empty

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description (Optional)')
    instructions = TextAreaField('Instructions (Optional)')
    # Example using SelectMultipleField - requires choices to be set in the route
    meal_type_suitability = SelectMultipleField(
        'Suitable for Meals (Optional)',
        choices=[('Breakfast','Breakfast'), ('Lunch','Lunch'), ('Dinner','Dinner'), ('Snack','Snack'), ('Any','Any')],
        option_widget=CheckboxInput(),
        widget=ListWidget(prefix_label=False),
        validators=[Optional()],
        description="Select one or more applicable meal types."
    )
    submit = SubmitField('Save Recipe Details')

# We won't create a separate 'Add Ingredient to Recipe' form *yet*.

class IngredientForm(FlaskForm):
    name = StringField('Ingredient Name', validators=[DataRequired(), Length(max=150)])
    category = StringField('Category', validators=[Optional(), Length(max=100)], description="e.g., Vegetable, Protein, Grain")
    typical_unit = StringField('Typical Unit for Recipes', default='g', validators=[DataRequired(), Length(max=50)], description="e.g., g, ml, piece, cup, slice")
    # Defines the amount the below nutrients refer to
    unit_quantity = FloatField('Nutrients Defined Per this Quantity of Unit', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])

    # --- Nutrition Fields (Optional) ---
    calories = FloatField('Est. Calories (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    protein = FloatField('Est. Protein (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    carbs = FloatField('Est. Carbs (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    fat = FloatField('Est. Fat (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    fiber = FloatField('Est. Fiber (g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    sugar = FloatField('Est. Sugar(g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    calcium = FloatField('Est. calcium(g) (per defined Qty)', validators=[Optional(), NumberRange(min=0)])
    # Add others if included in model

    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Ingredient')

class FoodForm(FlaskForm):
    name = StringField('Food Name', validators=[DataRequired(), Length(max=150)])
    base_unit = StringField('Base Unit (e.g., g, ml, cup, slice)', validators=[DataRequired(), Length(max=50)])
    base_quantity = FloatField('Nutrients Defined Per this Quantity', default=100.0, validators=[InputRequired(), NumberRange(min=0.001)])
    calories = FloatField('Calories (kcal)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    protein = FloatField('Protein (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    carbs = FloatField('Carbohydrates (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fat = FloatField('Fat (g)', default=0, validators=[InputRequired(), NumberRange(min=0)])
    fiber = FloatField('Fiber (g)', default=0, validators=[Optional(), NumberRange(min=0)])
    sugar = FloatField('Sugar (g)', default=0, validators=[Optional(), NumberRange(min=0)])
    calcium = FloatField('Calcium (mg)', default=0, validators=[Optional(), NumberRange(min=0)])
    
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
def calculate_recipe_nutrition(recipe_id):
    """Calculates and returns total estimated nutrition for a given recipe ID."""
    totals = {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0, 'fiber': 0.0, 'sugar':0.0, 'calcium':0.0} # Add others...
    recipe = Recipe.query.get(recipe_id)
    if not recipe:
        return None # Or raise error

    # Use lazy='dynamic' on ingredients relationship to query it here
    recipe_ingredients = recipe.ingredients # Eager load ingredient data

    for ri in recipe_ingredients:
        ingredient = ri.ingredient
        quantity_used = ri.quantity # This is in the ingredient's 'typical_unit'

        if not ingredient or ingredient.unit_quantity is None or ingredient.unit_quantity == 0:
            print(f"WARN: Skipping ingredient {ingredient.name if ingredient else 'ID unknown'} in recipe {recipe.id} due to missing base data.")
            continue # Skip if ingredient or its base data is missing

        # --- Calculate multiplier ---
        # Multiplier = (Quantity Used in Recipe / Quantity Nutrition is Defined For)
        try:
             multiplier = float(quantity_used) / float(ingredient.unit_quantity)
        except (ValueError, TypeError, ZeroDivisionError):
            print(f"WARN: Could not calculate multiplier for {ingredient.name} in recipe {recipe.id}. Skipping.")
            continue

        # --- Add ingredient's contribution to totals (handle None values) ---
        def safe_get_nutrient(val): return float(val) if val is not None else 0.0

        totals['calories'] += (safe_get_nutrient(ingredient.calories) * multiplier)
        totals['protein']  += (safe_get_nutrient(ingredient.protein) * multiplier)
        totals['carbs']    += (safe_get_nutrient(ingredient.carbs) * multiplier)
        totals['fat']      += (safe_get_nutrient(ingredient.fat) * multiplier)
        totals['fiber']    += (safe_get_nutrient(ingredient.fiber) * multiplier)
        totals['sugar']    += (safe_get_nutrient(ingredient.sugar) * multiplier)
        totals['calcium']    += (safe_get_nutrient(ingredient.calcium) * multiplier)
        # Add others...

    # Ensure final totals are finite numbers
    for key in totals:
        if not isinstance(totals[key], (int, float)) or not math.isfinite(totals[key]):
            totals[key] = 0.0 # Default to 0 if calculation failed somewhere

    return totals

def calculate_nutrients(food, quantity_consumed):
    """Calculates nutrients based on the logged quantity."""
    results = {
        'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0, 'fiber': 0.0, 'sugar':0.0, 'calcium':0.0
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
        results['sugar']      = safe_calc(food.sugar, multiplier)
        results['calcium']    = safe_calc(food.calcium, multiplier)
        # Calculate other nutrients here...

    except (TypeError, ValueError, ZeroDivisionError) as e:
        print(f"WARN: Error calculating nutrients: {e}")
        # Defaults are already set in results

    return results

def get_day_summary(log_date_obj):
    """Calculates total nutrients for a given date."""
    logs = MealLog.query.filter_by(log_date=log_date_obj).all()
    summary = { 'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0, 'fiber': 0, 'sugar':0, 'calcium':0 }
    for log in logs:
        summary['calories'] += log.calculated_calories or 0
        summary['protein'] += log.calculated_protein or 0
        summary['carbs'] += log.calculated_carbs or 0
        summary['fat'] += log.calculated_fat or 0
        summary['fiber'] += log.calculated_fiber or 0
        summary['sugar'] += log.calculated_sugar or 0
        summary['calcium'] += log.calculated_calcium or 0
        # Sum other nutrients...
    return summary

# --- Routes ---

# Main Route - Daily Log / Index / Ingredients
# ... (Keep existing routes like /log, /cache for now, we'll integrate/clean later) ...

# --- Virtual Fridge / Ingredient Management Routes ---
@app.route('/recipes')
def recipes_list():
    """Display a list of all created recipes."""
    recipes = Recipe.query.order_by(Recipe.name).all()
    return render_template('recipes_list.html', recipes=recipes) # New template

@app.route('/recipes/add', methods=['GET', 'POST'])
def add_recipe():
    """Add a new recipe (details only)."""
    form = RecipeForm()
    # You could pre-select 'Any' or leave blank depending on preference
    # if not form.meal_type_suitability.data: form.meal_type_suitability.data = ['Any']

    if form.validate_on_submit():
        try:
            new_recipe = Recipe(
                name=form.name.data.strip(),
                description=form.description.data,
                instructions=form.instructions.data,
                # Join selected meal types into a comma-separated string
                meal_type_suitability=",".join(form.meal_type_suitability.data) if form.meal_type_suitability.data else 'Any'
                # Nutrition totals will be calculated when ingredients are added/edited
            )
            db.session.add(new_recipe)
            db.session.commit()
            flash(f'Recipe "{new_recipe.name}" created. Now add ingredients.', 'success')
            # Redirect to the detail view to add ingredients
            return redirect(url_for('recipe_detail', recipe_id=new_recipe.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating recipe: {e}', 'danger')
            print(f"ERROR creating recipe: {e}")
    return render_template('add_edit_recipe.html', form=form, title="Create New Recipe", action_url=url_for('add_recipe')) # New template

@app.route('/recipes/<int:recipe_id>', methods=['GET'])
def recipe_detail(recipe_id):
    recipe = Recipe.query.options(
        db.selectinload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)
    ).get_or_404(recipe_id)

    # --- Instantiate the DEDICATED form class ---
    add_ingredient_form = AddIngredientToRecipeForm() # Use the new form

    # Populate ingredient choices (logic remains the same)
    current_ingredient_ids = {ri.ingredient_id for ri in recipe.ingredients}
    available_ingredients = Ingredient.query.filter(Ingredient.id.notin_(current_ingredient_ids)).order_by(Ingredient.name).all()
    # Set choices on the 'ingredient_id' field of the *instance*
    add_ingredient_form.ingredient_id.choices = [(ing.id, f"{ing.name} ({ing.typical_unit})") for ing in available_ingredients]

    return render_template('recipe_detail.html',
                           recipe=recipe,
                           add_ingredient_form=add_ingredient_form) # Pass the correctly bound form

@app.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    """Edit basic recipe details."""
    recipe = Recipe.query.get_or_404(recipe_id)
    # Pre-populate form, handling comma-separated string for meal types
    form = RecipeForm(obj=recipe)
    if request.method == 'GET': # Need to set SelectMultipleField data on GET
        form.meal_type_suitability.data = recipe.meal_type_suitability.split(',') if recipe.meal_type_suitability else []

    if form.validate_on_submit():
        try:
            recipe.name = form.name.data.strip()
            recipe.description = form.description.data
            recipe.instructions = form.instructions.data
            recipe.meal_type_suitability = ",".join(form.meal_type_suitability.data) if form.meal_type_suitability.data else 'Any'
            recipe.updated_at = datetime.utcnow()
            # Nutrition will be recalculated if ingredients change, or could force recalc here
            db.session.commit()
            flash(f'Recipe "{recipe.name}" details updated.', 'success')
            return redirect(url_for('recipe_detail', recipe_id=recipe.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating recipe details: {e}', 'danger')
            print(f"ERROR updating recipe {recipe_id}: {e}")
    # GET or failed POST
    return render_template('add_edit_recipe.html', # Re-use add_edit template
                           form=form,
                           title=f"Edit Recipe: {recipe.name}",
                           action_url=url_for('edit_recipe', recipe_id=recipe_id))


# Route to handle adding an ingredient to a recipe (called from recipe_detail)
@app.route('/recipes/<int:recipe_id>/add_ingredient', methods=['POST'])
def add_ingredient_to_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)

    # --- Instantiate the DEDICATED form class for POST validation ---
    form = AddIngredientToRecipeForm(request.form) # Pass request data

    # --- Repopulate choices BEFORE validation ---
    current_ingredient_ids = {ri.ingredient_id for ri in recipe.ingredients}
    available_ingredients = Ingredient.query.filter(Ingredient.id.notin_(current_ingredient_ids)).order_by(Ingredient.name).all()
    form.ingredient_id.choices = [(ing.id, f"{ing.name} ({ing.typical_unit})") for ing in available_ingredients]
    # Ensure the submitted value is actually in the choices for validation to pass if needed,
    # though coerce=int might handle it. If validation fails on ingredient_id, double check this.

    if form.validate_on_submit(): # Validate the dedicated form instance
        ingredient_id = form.ingredient_id.data
        quantity = form.quantity.data
        ingredient = Ingredient.query.get(ingredient_id)

        # --- Rest of the logic remains the same ---
        if not ingredient:
             flash("Selected ingredient not found.", 'danger')
        else:
            try:
                # Check if already exists...
                existing_ri = RecipeIngredient.query.filter_by(recipe_id=recipe_id, ingredient_id=ingredient_id).first()
                if existing_ri:
                    flash(f"{ingredient.name} is already in this recipe.", 'warning')
                else:
                    # 1. Create the new RecipeIngredient object
                    new_ri = RecipeIngredient(
                        recipe_id=recipe_id,
                        ingredient_id=ingredient_id,
                        quantity=quantity
                    )
                    # 2. ADD the new object to the session - Marks it for insertion
                    db.session.add(new_ri)

                    # 3. FLUSH the session - Sends pending changes (the INSERT for new_ri)
                    # to the database BUT doesn't permanently commit the transaction yet.
                    # This is useful if subsequent operations (like calculation) might fail,
                    # allowing a full rollback. It also ensures new_ri gets its ID if needed.
                    db.session.flush()

                    # 4. EXPIRE the related Recipe object - Tells SQLAlchemy the current
                    # 'recipe' Python object might be stale regarding its 'ingredients' list.
                    db.session.expire(recipe)

                    # 5. Recalculate nutrition - Accessing recipe.ingredients inside this
                    # function will now trigger SQLAlchemy to reload the ingredients list
                    # from the DB (including the newly flushed 'new_ri').
                    updated_totals = calculate_recipe_nutrition(recipe_id)
                    if updated_totals:
                        recipe.total_calories = updated_totals['calories']
                        recipe.total_protein = updated_totals['protein']
                        recipe.total_carbs = updated_totals['carbs']
                        recipe.total_fat = updated_totals['fat']
                        recipe.total_fiber = updated_totals['fibre']
                        recipe.total_sugar = updated_totals['sugar']
                        recipe.total_calcium = updated_totals['calcium']
                        recipe.updated_at = datetime.utcnow()
                        # ... set other totals ...
                        recipe.updated_at = datetime.utcnow()
                    else:
                         flash("Could not recalculate recipe totals.", "warning")

                    # 6. COMMIT the transaction - Makes all changes permanent in the DB
                    # (the new RecipeIngredient and the updated Recipe totals).
                    db.session.commit()
                    flash(f"Added {quantity} {ingredient.typical_unit} of {ingredient.name} to recipe.", 'success')

            except Exception as e:
                # 7. ROLLBACK if any error occurred during steps 1-6
                db.session.rollback()
                flash(f"Error adding ingredient to recipe: {e}", 'danger')
                print(f"ERROR adding ingredient to recipe {recipe_id}: {e}")
    else:
         # Collect validation errors for flashing (optional)
         error_messages = []
         for field, errors in form.errors.items():
             for error in errors:
                 error_messages.append(f"{getattr(form, field).label.text}: {error}")
         flash("Error adding ingredient: " + "; ".join(error_messages), "danger")


    return redirect(url_for('recipe_detail', recipe_id=recipe_id))

# Route to remove an ingredient from a recipe
@app.route('/recipes/remove_ingredient/<int:recipe_ingredient_id>', methods=['POST'])
def remove_ingredient_from_recipe(recipe_ingredient_id):
    ri = RecipeIngredient.query.options(db.joinedload(RecipeIngredient.ingredient)).get_or_404(recipe_ingredient_id)
    recipe_id = ri.recipe_id # Get recipe ID before deleting
    ingredient_name = ri.ingredient.name if ri.ingredient else 'Ingredient'
    try:
        db.session.delete(ri)

        db.session.flush()

        # --- Recalculate and Update Recipe Totals ---
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
                recipe.total_sugar = updated_totals['sugar']
                recipe.total_calcium = updated_totals['calcium']
                # Update others...
                recipe.updated_at = datetime.utcnow()
            else:
                 recipe.total_calories = 0
                 recipe.total_protein = 0
                 flash("Could not recalculate recipe totals.", "warning")
                 # Set totals to None/0 if desired when empty?
                 # recipe.total_calories = None ... etc ...
        db.session.commit()
        flash(f"Removed {ingredient_name} from recipe.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing ingredient: {e}", "danger")
        print(f"ERROR removing ingredient link {recipe_ingredient_id}: {e}")

    return redirect(url_for('recipe_detail', recipe_id=recipe_id))


@app.route('/recipes/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    """Delete a recipe and its ingredient links."""
    recipe = Recipe.query.get_or_404(recipe_id)
    recipe_name = recipe.name
    try:
        # Deleting recipe automatically deletes RecipeIngredient links due to cascade
        db.session.delete(recipe)
        db.session.commit()
        flash(f'Recipe "{recipe_name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting recipe: {e}', 'danger')
        print(f"ERROR deleting recipe {recipe_id}: {e}")
    return redirect(url_for('recipes_list'))


@app.route('/ingredients')
def ingredients_list():
    ingredients = Ingredient.query.order_by(Ingredient.category, Ingredient.name).all()
    return render_template('ingredients_list.html', ingredients=ingredients) # New template needed

@app.route('/ingredients/add', methods=['GET', 'POST'])
def add_ingredient():
    form = IngredientForm()
    if form.validate_on_submit():
        existing_ingredient = Ingredient.query.filter(db.func.lower(Ingredient.name) == form.name.data.strip().lower()).first()
        if existing_ingredient:
            flash('An ingredient with this name already exists.', 'danger')
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
                    sugar=form.sugar.data if form.sugar.data is not None else None,
                    calcium=form.calcium.data if form.calcium.data is not None else None,
                    notes=form.notes.data,
                    # created_at is handled by default
                    updated_at=datetime.utcnow() # Set initial updated_at
                )
                db.session.add(new_ingredient)
                db.session.commit()
                flash(f'Ingredient "{new_ingredient.name}" added.', 'success')
                return redirect(url_for('ingredients_list'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding ingredient: {e}', 'danger')
                print(f"ERROR adding ingredient: {e}")
    return render_template('add_edit_ingredient.html', # New template needed
                           form=form,
                           title='Add New Ingredient',
                           action_url=url_for('add_ingredient'))

@app.route('/ingredients/edit/<int:ingredient_id>', methods=['GET', 'POST'])
def edit_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    form = IngredientForm(obj=ingredient) # Pre-populate form

    if form.validate_on_submit():
        new_name_lower = form.name.data.strip().lower()
        existing_conflict = Ingredient.query.filter(
            db.func.lower(Ingredient.name) == new_name_lower,
            Ingredient.id != ingredient_id
        ).first()
        if existing_conflict:
            flash('Another ingredient with this name already exists.', 'danger')
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
                sugar=form.sugar.data if form.sugar.data is not None else None
                calcium=form.calcium.data if form.calcium.data is not None else None
                ingredient.notes = form.notes.data
                ingredient.updated_at = datetime.utcnow() # Update timestamp

                db.session.commit()
                flash(f'Ingredient "{ingredient.name}" updated.', 'success')
                return redirect(url_for('ingredients_list'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating ingredient: {e}', 'danger')
                print(f"ERROR updating ingredient {ingredient_id}: {e}")
    return render_template('add_edit_ingredient.html', # Use new template
                           form=form,
                           title=f'Edit Ingredient: {ingredient.name}',
                           action_url=url_for('edit_ingredient', ingredient_id=ingredient_id))

@app.route('/ingredients/delete/<int:ingredient_id>', methods=['POST'])
def delete_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    ingredient_name = ingredient.name
    # Later check if used in recipes
    try:
        db.session.delete(ingredient)
        db.session.commit()
        flash(f'Ingredient "{ingredient_name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting ingredient: {e}', 'danger')
        print(f"ERROR deleting ingredient {ingredient_id}: {e}")
    return redirect(url_for('ingredients_list'))

# ... (Rest of your routes: daily_log, cache, units, etc.) ...

# Update db.create_all() call location if necessary (ensure it's run)
with app.app_context():
     print("Checking/creating database tables...")
     try:
         db.create_all() # This will now also create the 'ingredients' table
         print("Database tables checked/created.")
     except Exception as e:
         print(f"ERROR during db.create_all(): {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

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
                calculated_fiber=calculated.get('fiber', 0.0),
                calculated_sugar=calculated.get('sugar',0.0),
                calculated_calcium=calculated.get('calcium',0.0)
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
                    sugar=form.sugar.data,
                    calcium=form.calcium.data,
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
                food.sugar=form.sugar.data
                food.calcium=form.calcium.data
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
