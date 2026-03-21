import sqlite3 # Library to interact with SQLite databases

import os # Provides access to operating system functions

from groq import Groq # Groq client for accessing the LLaMA AI model
# pip install groq

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response # Flask web framework tools
# pip install flask

from datetime import datetime, timedelta # For working with dates and time differences

# Library for generating PDF files
from fpdf import FPDF
# pip install fpdf

#loading api key from .env file :)
# python3 -m pip install python-dotenv
# import os is already done above
from dotenv import load_dotenv


# Creates the Flask web application instance
app = Flask(__name__)

# Initialises the Groq AI client with the API key
client = None

load_dotenv()
groq_key = os.getenv("GROQ_KEY")
supersecret = os.getenv("supersecret")
if not groq_key:
    print("GROQ KEY IMPORT ERROR!!")
else:
    client = Groq(api_key=groq_key)
    if client is not None:
        print("API for Groq imported.")

# Secret key used to sign and encrypt session cookies
app.secret_key = str(supersecret)


# ─── MERGE SORT ────────────────────────────────────────────────────────────────

# Recursively sorts two parallel lists (names + values) together
def merge_sort_parallel(names, values, reverse=False):
    # Base case: a list of 0 or 1 items is already sorted
    if len(values) <= 1:
        # Return as-is, nothing to sort
        return names, values
    # Find the midpoint to split the list in half
    mid = len(values) // 2
    # Recursively sort the left half
    left_names, left_values = merge_sort_parallel(names[:mid], values[:mid], reverse)
    # Recursively sort the right half
    right_names, right_values = merge_sort_parallel(names[mid:], values[mid:], reverse)
    # Merge the two sorted halves
    return merge_parallel(left_names, left_values, right_names, right_values, reverse)

# Merges two sorted halves back into one sorted list
def merge_parallel(left_n, left_v, right_n, right_v, reverse):
    # Initialise empty result lists for names and values
    res_n, res_v = [], []
    # i = pointer for left half, j = pointer for right half
    i = j = 0
    # Keep going while both halves still have elements
    while i < len(left_v) and j < len(right_v):
        # Compare elements; flip condition if sorting in reverse
        condition = left_v[i] <= right_v[j] if not reverse else left_v[i] >= right_v[j]
        # If left element should come first
        if condition:
            # Add left value and name to result, move left pointer forward
            res_v.append(left_v[i]); res_n.append(left_n[i]); i += 1
        # Otherwise right element should come first
        else:
            # Add right value and name to result, move right pointer forward
            res_v.append(right_v[j]); res_n.append(right_n[j]); j += 1
    # Append any remaining elements from either half (already sorted)
    res_v += left_v[i:] + right_v[j:]
    # Append their corresponding names
    res_n += left_n[i:] + right_n[j:]
    # Return the fully merged and sorted parallel lists
    return res_n, res_v

# ─── DATABASE ──────────────────────────────────────────────────────────────────

def get_db():
    # Connect to (or create) the SQLite database file
    conn = sqlite3.connect('database.db')
    # Makes rows behave like dicts so columns can be accessed by name
    conn.row_factory = sqlite3.Row
    # Enforces foreign key constraints in SQLite (off by default)
    conn.execute("PRAGMA foreign_keys = ON")
    # Returns the connection object for use in routes
    return conn

# ─── RESET LOGIC ───────────────────────────────────────────────────────────────

def get_last_reset_week():
    """Reads the last reset week string from the app_state table in the DB."""
    # Open a direct database connection
    connection = sqlite3.connect('database.db')
    # Create a cursor to execute SQL statements
    cursor = connection.cursor()
    try:
        # Create app_state table if it doesn't exist yet
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Save the new table if it was just created
        connection.commit()
        # Try to fetch the last reset week value
        row = cursor.execute(
            "SELECT value FROM app_state WHERE key = 'last_reset_week'"
        ).fetchone()
        # Return the value if it exists, otherwise None
        return row[0] if row else None
    finally:
        # Always close the connection
        connection.close()

def set_last_reset_week(week_str):
    """Saves the last reset week string into the app_state table in the DB."""
    # Open a direct database connection
    connection = sqlite3.connect('database.db')
    # Create a cursor to execute SQL statements
    cursor = connection.cursor()
    try:
        # Create app_state table if it doesn't exist yet
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Insert or update the last reset week value
        cursor.execute("""
            INSERT INTO app_state (key, value) VALUES ('last_reset_week', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (week_str,))
        # Save the change to the database
        connection.commit()
    finally:
        # Always close the connection
        connection.close()

def reset_expenses(sunday_str, is_first_week):
    """
    Inserts a fresh baseline record for every expense item, dated to this week's Sunday.
    First week of month: Fixed items → default_amount, Unfixed → 0
    Other weeks:         Everything → 0
    """
    # Open a direct database connection
    connection = sqlite3.connect('database.db')
    # Create a cursor to execute SQL statements
    cursor = connection.cursor()
    # Attempt the reset operations
    try:
        # If it's the first week of the month
        if is_first_week:
            # Fixed items get their default amount, unfixed items get 0
            cursor.execute("""
                INSERT INTO expense_records (item_id, amount, date)
                SELECT item_id,
                       CASE WHEN type = 'Fixed' THEN default_amount ELSE 0 END,
                       ?
                FROM expense_items
            """, (sunday_str,))
        # Any other week of the month
        else:
            # All items reset to 0
            cursor.execute("""
                INSERT INTO expense_records (item_id, amount, date)
                SELECT item_id, 0, ?
                FROM expense_items
            """, (sunday_str,))
        # Save all changes to the database
        connection.commit()
    # If any SQL error occurs
    except sqlite3.Error as e:
        # Print the error message without crashing the app
        print(f"Reset error: {e}")
    # Always runs regardless of success or failure
    finally:
        # Close the database connection to free resources
        connection.close()

# ─── GLOBAL RESET CHECK ────────────────────────────────────────────────────────

@app.before_request
def check_for_weekly_reset():
    """
    Runs automatically before every request.
    Uses the DB (not session/cookies) to track the last reset week,
    so it works reliably even if the user clears their browser.
    Always resets using this week's Sunday as the record date so
    BETWEEN queries on sun_str/sat_str work correctly on all pages.
    """
    # Only run reset logic if the user is logged in
    if not session.get('login'):
        return

    # Get today's date
    today = datetime.now().date()

    # Calculate this week's Sunday
    days_since_sunday = (today.weekday() + 1) % 7
    this_sunday = today - timedelta(days=days_since_sunday)
    # Format Sunday as a string for use in SQL queries
    this_sunday_str = this_sunday.strftime('%Y-%m-%d')

    # Build a week identifier string e.g. '2026-W11'
    current_year, current_week, _ = today.isocalendar()
    week_str = f"{current_year}-W{current_week}"

    # Check the DB (not session) for when we last reset
    last_reset_week = get_last_reset_week()

    # Only reset if this is a new week we haven't reset for yet
    if last_reset_week != week_str:
        # First week of month = Sunday falls on day 1–7
        is_first_week = this_sunday.day <= 7
        # Run the reset, dated to this week's Sunday
        reset_expenses(this_sunday_str, is_first_week)
        # Save the new week to the DB so it persists across browser sessions
        set_last_reset_week(week_str)
        # Log the reset to the terminal
        print(f"Weekly reset triggered for {this_sunday_str} (first_week={is_first_week})")

# ─── AI HELPERS ────────────────────────────────────────────────────────────────

# Generates an AI motivational message based on spending
def get_savings_insight(current_spent, all_time_spent):
    # Attempt the API call
    try:
        # Send a request to the Groq AI API
        chat_completion = client.chat.completions.create(
            # Specifies which AI model to use
            model="llama-3.3-70b-versatile",
            messages=[
                # System prompt restricts AI to budget topics only
                {"role": "system", "content": "You are a personal budget coach. You will be provided with a user's spending data. Give specific, concise, and helpful advice. If the user asks about ANYTHING unrelated to budgeting, personal finance, or spending, respond only with: 'Invalid topic. I can only help with budgeting and financial advice"},
                # User prompt with actual spending data
                {"role": "user", "content": f"I spent ${current_spent} this month. My all-time average is ${all_time_spent}. Give me one short, punchy sentence of motivation."}
            ]
        )
        # Extract and return the AI's text response
        return chat_completion.choices[0].message.content
    # If the API call fails for any reason
    except:
        # Return a safe fallback message
        return "Keep saving to reach your long-term goals!"

# ─── ROUTES ────────────────────────────────────────────────────────────────────

# Defines the URL route for the home page
@app.route('/home')
def home():
    # Check if the user is logged in via session
    if not session.get('login'):
        # If not, redirect to login page
        return redirect('/')

    # Get today's date
    today = datetime.now().date()
    # Calculate how many days ago Sunday was (weekday() gives Mon=0, so +1 % 7 gives Sun=0)
    days_since_sunday = (today.weekday() + 1) % 7
    # Get this week's Sunday as a formatted string
    sun_str = (today - timedelta(days=days_since_sunday)).strftime('%Y-%m-%d')
    # Get this week's Saturday as a formatted string
    sat_str = (today - timedelta(days=days_since_sunday) + timedelta(days=6)).strftime('%Y-%m-%d')
    # Get current month in 'YYYY-MM' format
    current_month = datetime.now().strftime('%Y-%m')

    # Open database connection
    conn = get_db()

    # Get only the latest running total per item for this week
    # Uses MAX(record_id) subquery to respect append-only records
    rows = conn.execute("""
        SELECT c.name AS category, SUM(latest.amount) AS total
        FROM categories c
        JOIN expense_items ei ON c.category_id = ei.category_id
        JOIN (
            SELECT item_id, amount
            FROM expense_records
            WHERE record_id IN (
                SELECT MAX(record_id)
                FROM expense_records
                WHERE date BETWEEN ? AND ?
                GROUP BY item_id
            )
        ) latest ON ei.item_id = latest.item_id
        WHERE c.name != 'discretionary_cash'
        GROUP BY c.name
    """, (sun_str, sat_str)).fetchall()

    # Get only the latest running total per item for this month
    # Uses MAX(record_id) subquery to respect append-only records
    monthly_result = conn.execute("""
        SELECT SUM(latest.amount)
        FROM categories c
        JOIN expense_items ei ON c.category_id = ei.category_id
        JOIN (
            SELECT item_id, amount
            FROM expense_records
            WHERE record_id IN (
                SELECT MAX(record_id)
                FROM expense_records
                WHERE strftime('%Y-%m', date) = ?
                GROUP BY item_id
            )
        ) latest ON ei.item_id = latest.item_id
        WHERE c.name != 'discretionary_cash'
    """, (current_month,)).fetchone()[0]

    # Close the database connection
    conn.close()

    # Build a dict of category → amount, defaulting to 0 if null
    raw_data = {row['category']: row['total'] or 0 for row in rows}
    # Sum all category amounts for the weekly total
    weekly_grand_total = sum(raw_data.values())
    # Use 0 if monthly result is null
    monthly_grand_total = monthly_result or 0

    # Extract category names as a list
    categories = list(raw_data.keys())
    # Extract amounts as a list
    amounts = list(raw_data.values())

    # Get the sort parameter from the URL (e.g. ?sort=asc)
    sort_order = request.args.get('sort')
    # Only sort if a valid sort direction is given
    if sort_order in ['asc', 'desc']:
        # Sort both lists together using merge sort
        categories, amounts = merge_sort_parallel(categories, amounts, reverse=(sort_order == 'desc'))

    # Re-pair the (possibly sorted) categories and amounts into a dict
    category_totals = dict(zip(categories, amounts))
    # Calculate each category's percentage of the weekly total
    percentages = {t: (round((a / weekly_grand_total) * 100) if weekly_grand_total > 0 else 0)
                   for t, a in category_totals.items()}

    # Render the home template with all calculated data
    return render_template('home.html',
                           grand_total=weekly_grand_total,
                           monthly_total=monthly_grand_total,
                           category_totals=category_totals,
                           percentages=percentages)


@app.route('/edit')
def edit_expenses():
    # Check if the user is logged in via session
    if not session.get('login'):
        return redirect('/')

    # Open database connection
    conn = get_db()
    # Get latest record per item using append-only MAX(record_id) pattern
    # Uses a subquery join (same pattern as /home and /graph) to correctly
    # scope MAX(record_id) per item — avoids SQLite correlated subquery issues
    rows = conn.execute("""
        SELECT c.name AS category,
               ei.item_id, ei.name AS item_name, ei.type,
               ei.default_amount,
               COALESCE(latest.amount, 0) AS current_spent
        FROM expense_items ei
        JOIN categories c ON ei.category_id = c.category_id
        LEFT JOIN (
            SELECT item_id, amount
            FROM expense_records
            WHERE record_id IN (
                SELECT MAX(record_id)
                FROM expense_records
                GROUP BY item_id
            )
        ) latest ON ei.item_id = latest.item_id
        ORDER BY c.category_id, ei.item_id
    """).fetchall()
    # Close the database connection
    conn.close()

    # Dictionary to group items by category
    all_data = {}
    for row in rows:
        # Get the category name
        cat = row['category']
        # If category not yet in dict, initialise it
        if cat not in all_data:
            all_data[cat] = {'rows': [], 'fixed_total': 0}
        # Add item to category
        all_data[cat]['rows'].append(row)
        # Sum the default amounts (Monthly Values) for the category total
        all_data[cat]['fixed_total'] += row['default_amount']

    # Render the edit template with grouped data
    return render_template('edit.html', data=all_data)


# Defines the URL route for the AI chat page
@app.route('/chat')
def chat():
    # Check if user is logged in
    if not session.get('login'):
        # Redirect to login if not
        return redirect('/')
    # Render the chat template
    return render_template('chat.html')


# API endpoint that receives chat messages via POST
@app.route("/get_ai_response", methods=["POST"])
def get_ai_response():
    # Check if user is logged in
    if not session.get('login'):
        # Return 401 Unauthorized if not
        return jsonify({"response": "Please log in first!"}), 401

    # Extract the user's message from the JSON request body
    user_message = request.json.get("message")

    # Open database connection
    conn = get_db()
    # Get the latest spending total per category
    rows = conn.execute("""
        SELECT c.name AS category, SUM(er.amount) AS total
        FROM expense_records er
        JOIN expense_items ei ON er.item_id = ei.item_id
        JOIN categories c ON ei.category_id = c.category_id
        WHERE er.record_id IN (
            SELECT MAX(record_id) FROM expense_records GROUP BY item_id
        )
        GROUP BY c.name
    """).fetchall()
    # Close the database connection
    conn.close()

    # Format spending data as a readable string for the AI
    summary = "".join([f"- {row['category'].capitalize()}: ${row['total']}\n" for row in rows])

    # Attempt the API call
    try:
        # Send a request to the Groq AI API
        chat_completion = client.chat.completions.create(
            # Specifies the AI model to use
            model="llama-3.3-70b-versatile",
            messages=[
                # System prompt defining AI behaviour
                {"role": "system", "content": "You are a personal budget coach. You will be provided with a user's spending data. Give specific, concise, and helpful advice."},
                # User message with spending context attached
                {"role": "user", "content": f"Here is my current spending:\n{summary}\n\nMy question: {user_message}"}
            ],
            # Controls randomness of AI responses (0=deterministic, 1=very random)
            temperature=0.7,
        )
        # Return AI response as JSON
        return jsonify({"response": chat_completion.choices[0].message.content})
    # If the API call fails
    except Exception as e:
        # Log the error
        print(f"Groq AI Error: {e}")
        # Return a safe fallback response
        return jsonify({"response": "Something went wrong"})


# Defines the URL route for the goals page
@app.route('/goals')
def goals():
    # Check if user is logged in
    if not session.get('login'):
        # Redirect to login if not
        return redirect('/')

    # Get the view type from URL (default to 'budget')
    view = request.args.get('view', 'budget')
    # Open database connection
    conn = get_db()
    # List to hold budget comparison data
    budget_data = []
    # Total spent this month (used in 'saved' view)
    monthly_spent = 0
    # Historical average monthly spending
    avg_monthly = 0
    # AI motivational message
    ai_insight = ""

    # If showing the budget limits view
    if view == 'budget':
        # Get current month
        current_month = datetime.now().strftime('%Y-%m')
        rows = conn.execute("""
            SELECT c.category_id, c.name AS category,
                   g.monthly_limit,
                   SUM(er.amount) AS actual
            FROM categories c
            LEFT JOIN goals g ON c.category_id = g.category_id
            LEFT JOIN expense_items ei ON c.category_id = ei.category_id
            LEFT JOIN expense_records er ON ei.item_id = er.item_id
                AND strftime('%Y-%m', er.date) = ?
                AND er.record_id IN (
                    SELECT MAX(record_id) FROM expense_records GROUP BY item_id
                )
            GROUP BY c.category_id
        """, (current_month,)).fetchall()

        # Loop through each category
        for row in rows:
            # Get the budget limit, default to 0
            limit = row['monthly_limit'] or 0
            # Get actual spending, default to 0
            actual = row['actual'] or 0
            # Calculate remaining budget, never goes below 0
            remaining = max(0, limit - actual)
            # Calculate % of budget remaining
            percent_left = round((remaining / limit * 100), 1) if limit > 0 else 0
            # Add this category's data to the list
            budget_data.append({
                # Format category name nicely
                'name': row['category'].replace('_', ' ').capitalize(),
                # Raw category name for form submissions
                'id': row['category'],
                # Monthly budget limit
                'limit': limit,
                # Amount spent so far
                'spent': actual,
                # Amount left in budget
                'remaining': remaining,
                # Percentage of budget remaining
                'percent': percent_left
            })

    # If showing the savings comparison view
    elif view == 'saved':
        # Get current datetime
        today = datetime.now()
        # Get the current day number
        current_day = today.day
        # Get current month string
        current_month = today.strftime('%Y-%m')

        # Get total spent so far this month up to today's day number
        monthly_spent = conn.execute("""
            SELECT SUM(er.amount)
            FROM expense_records er
            WHERE strftime('%Y-%m', er.date) = ?
              AND CAST(strftime('%d', er.date) AS INTEGER) <= ?
        """, (current_month, current_day)).fetchone()[0] or 0

        # Get totals from all past months up to the same day number
        past_months = conn.execute("""
            SELECT strftime('%Y-%m', er.date) AS month, SUM(er.amount)
            FROM expense_records er
            WHERE strftime('%Y-%m', er.date) != ?
              AND CAST(strftime('%d', er.date) AS INTEGER) <= ?
            GROUP BY month
        """, (current_month, current_day)).fetchall()

        # Extract just the totals from the results
        monthly_totals = [r[1] for r in past_months]
        # Calculate average, avoiding division by zero
        avg_monthly = sum(monthly_totals) / len(monthly_totals) if monthly_totals else 0
        # Generate AI motivational message
        ai_insight = get_savings_insight(monthly_spent, avg_monthly)

    # Close the database connection
    conn.close()
    # Render goals template with all computed data
    return render_template('goals.html',
                           view=view,
                           budget_data=budget_data,
                           saved_this_month=monthly_spent,
                           avg_monthly=round(avg_monthly, 2),
                           ai_insight=ai_insight,
                           categories_list=[r['id'] for r in budget_data] if budget_data else [])


# Endpoint to update a category's monthly budget limit
@app.route('/update_goal', methods=['POST'])
def update_goal():
    # Get the category name from the submitted form
    cat = request.form.get('category')
    # Get the new budget limit value from the form
    new_limit = request.form.get('limit')
    # Open database connection
    conn = get_db()
    # Update the monthly limit for this category
    conn.execute("""
        UPDATE goals SET monthly_limit = ?
        WHERE category_id = (SELECT category_id FROM categories WHERE name = ?)
    """, (new_limit, cat))
    # Save the change to the database
    conn.commit()
    # Close the database connection
    conn.close()
    # Redirect back to the budget view
    return redirect('/goals?view=budget')


# Defines the URL route for the graph page
@app.route('/graph')
def graph():
    # Check if user is logged in
    if not session.get('login'):
        # Redirect to login if not
        return redirect('/')

    try:
        # Get week offset from URL (0 = current week, -1 = last week, etc.)
        week_offset = int(request.args.get('week', 0))
    except (ValueError, TypeError):
        # Default to 0 if invalid value provided
        week_offset = 0

    # Get today's date
    today = datetime.now().date()
    # Calculate days since last Sunday
    days_since_sunday = (today.weekday() + 1) % 7
    # Calculate the Sunday of the target week
    target_sunday = today - timedelta(days=days_since_sunday) + timedelta(weeks=week_offset)
    # Calculate the Saturday of the target week
    target_saturday = target_sunday + timedelta(days=6)
    # Format Sunday as a string
    sun_str = target_sunday.strftime('%Y-%m-%d')
    # Format Saturday as a string
    sat_str = target_saturday.strftime('%Y-%m-%d')

    # Get selected category from URL (if any)
    selected_category = request.args.get('category')
    # Open database connection
    conn = get_db()
    # Check if the selected category actually exists in the database
    valid_cat = conn.execute("SELECT 1 FROM categories WHERE name = ?", (selected_category,)).fetchone()

    # If a valid category was selected
    if valid_cat:
        # Get latest running total per item for the selected week
        rows = conn.execute("""
            SELECT ei.name, latest.amount AS amount
            FROM expense_items ei
            JOIN categories c ON ei.category_id = c.category_id
            JOIN (
                SELECT item_id, amount
                FROM expense_records
                WHERE record_id IN (
                    SELECT MAX(record_id)
                    FROM expense_records
                    WHERE date BETWEEN ? AND ?
                    GROUP BY item_id
                )
            ) latest ON ei.item_id = latest.item_id
            WHERE c.name = ?
        """, (sun_str, sat_str, selected_category)).fetchall()
        # Extract item names as chart labels
        labels = [r['name'] for r in rows]
        # Extract amounts as chart values
        values = [r['amount'] or 0 for r in rows]
        # Set chart title to category name
        display_title = f"{selected_category.replace('_', ' ').capitalize()} Details"
    # If no valid category selected, show overall view
    else:
        # Get latest running total per category for the week
        rows = conn.execute("""
            SELECT c.name AS category, SUM(latest.amount) AS total
            FROM categories c
            JOIN expense_items ei ON c.category_id = ei.category_id
            JOIN (
                SELECT item_id, amount
                FROM expense_records
                WHERE record_id IN (
                    SELECT MAX(record_id)
                    FROM expense_records
                    WHERE date BETWEEN ? AND ?
                    GROUP BY item_id
                )
            ) latest ON ei.item_id = latest.item_id
            GROUP BY c.name
            ORDER BY c.category_id
        """, (sun_str, sat_str)).fetchall()
        # Format category names as labels
        labels = [r['category'].replace('_', ' ').capitalize() for r in rows]
        # Extract totals as chart values
        values = [r['total'] or 0 for r in rows]
        # Set chart title to overall
        display_title = "Overall Spending"

    # Close the database connection
    conn.close()
    # Format week range for display
    week_display = f"{target_sunday.strftime('%b %d')} - {target_saturday.strftime('%b %d')}"

    # Render graph template with chart data
    return render_template('graph.html',
                           labels=labels,
                           values=values,
                           week_label=week_display,
                           current_offset=week_offset,
                           current_cat=selected_category,
                           display_title=display_title)


# Defines the URL route for the report page
@app.route('/report')
def report():
    # Check if user is logged in
    if not session.get('login'):
        # Redirect to login if not
        return redirect('/')

    # List to hold available report date ranges
    reports_list = []
    # Get today's date
    today = datetime.now().date()
    # Get day of week (Mon=0, Sun=6)
    current_day_of_week = today.weekday()
    # Calculate days since last Sunday
    days_since_sunday = (today.weekday() + 1) % 7
    # Get this week's Sunday
    this_sunday = today - timedelta(days=days_since_sunday)
    # Get last week's Sunday
    last_sunday = this_sunday - timedelta(weeks=1)
    # Get last week's Saturday
    last_saturday = last_sunday + timedelta(days=6)

    # Always add last week's report as available
    reports_list.append({
        # Human-readable date range
        'range': f"{last_sunday.strftime('%b %d, %Y')} - {last_saturday.strftime('%b %d, %Y')}",
        # Start date for PDF query
        'start': last_sunday.strftime('%Y-%m-%d'),
        # Marks the report as ready to download
        'ready': True
    })

    # If today is Saturday (end of current week)
    if current_day_of_week == 5:
        # Calculate this week's Saturday
        this_saturday = this_sunday + timedelta(days=6)
        # Also add this week's report
        reports_list.append({
            'range': f"{this_sunday.strftime('%b %d, %Y')} - {this_saturday.strftime('%b %d, %Y')}",
            'start': this_sunday.strftime('%Y-%m-%d'),
            'ready': True
        })

    # Render report page with available reports
    return render_template('report.html', reports=reports_list)


# Endpoint to generate and download a PDF report
@app.route('/download_pdf')
def download_pdf():
    # Get the start date from the URL
    start_str = request.args.get('start')
    # Parse it into a date object
    start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
    # Calculate end date (6 days later = full week)
    end_date = start_date + timedelta(days=6)
    # Format end date as string
    end_str = end_date.strftime('%Y-%m-%d')

    # Create a new PDF document
    pdf = FPDF()
    # Add a blank page
    pdf.add_page()
    # Set font to bold Arial size 20
    pdf.set_font("Arial", 'B', 20)
    # Set text colour to dark blue-grey
    pdf.set_text_color(75, 85, 106)
    # Add centred report title
    pdf.cell(190, 15, "ZHUHU EXPENSE WEEKLY REPORT", ln=True, align='C')
    # Switch to italic Arial size 12
    pdf.set_font("Arial", 'I', 12)
    # Add date range subtitle
    pdf.cell(190, 10, f"Period: {start_date.strftime('%b %d')} to {end_date.strftime('%b %d, %Y')}", ln=True, align='C')
    # Add vertical spacing
    pdf.ln(10)

    # Set font for table headers
    pdf.set_font("Arial", 'B', 11)
    # Set header background to light blue
    pdf.set_fill_color(212, 224, 250)
    # Draw category column header
    pdf.cell(40, 10, " CATEGORY", 1, 0, 'L', True)
    # Draw item name column header
    pdf.cell(85, 10, " ITEM NAME", 1, 0, 'L', True)
    # Draw type column header
    pdf.cell(30, 10, " TYPE", 1, 0, 'C', True)
    # Draw amount column header
    pdf.cell(35, 10, " AMOUNT", 1, 1, 'C', True)

    # Open database connection
    conn = get_db()
    # Get latest running total per item for the report week
    rows = conn.execute("""
        SELECT c.name AS category, ei.name AS item_name, ei.type, latest.amount AS amount
        FROM expense_items ei
        JOIN categories c ON ei.category_id = c.category_id
        JOIN (
            SELECT item_id, amount
            FROM expense_records
            WHERE record_id IN (
                SELECT MAX(record_id)
                FROM expense_records
                WHERE date BETWEEN ? AND ?
                GROUP BY item_id
            )
        ) latest ON ei.item_id = latest.item_id
        ORDER BY c.category_id, ei.item_id
    """, (start_str, end_str)).fetchall()
    # Close the database connection
    conn.close()

    # Running total for all expenses in the report
    grand_total = 0
    # Switch to regular size 10 for table rows
    pdf.set_font("Arial", size=10)
    # Loop through each expense item
    for row in rows:
        # Write category name
        pdf.cell(40, 10, f" {row['category'].replace('_', ' ').capitalize()}", 1)
        # Write item name (truncated to 35 chars)
        pdf.cell(85, 10, f" {row['item_name'][:35]}", 1)
        # Write Fixed/Unfixed type
        pdf.cell(30, 10, row['type'], 1, 0, 'C')
        # Write formatted amount
        pdf.cell(35, 10, f"${row['amount']:,.2f}", 1, 1, 'R')
        # Add to running grand total
        grand_total += row['amount']

    # Add spacing before total row
    pdf.ln(5)
    # Bold font for total line
    pdf.set_font("Arial", 'B', 12)
    # Label aligned right
    pdf.cell(155, 10, "WEEKLY GRAND TOTAL: ", 0, 0, 'R')
    # Change colour to red-brown for emphasis
    pdf.set_text_color(137, 65, 61)
    # Write the grand total
    pdf.cell(35, 10, f"${grand_total:,.2f}", 0, 1, 'R')

    # Generate PDF as bytes and wrap in HTTP response
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    # Tell browser to download the file
    response.headers.set('Content-Disposition', 'attachment', filename=f'Zhuhu_Report_{start_str}.pdf')
    # Set MIME type to PDF
    response.headers.set('Content-Type', 'application/pdf')
    # Send the PDF file to the client
    return response


# Defines the login page route, accepts both GET and POST
@app.route("/", methods=["GET", "POST"])
def login():
    error = None  # no error by default
    if request.method == "POST":
        # Get entered password
        password = request.form.get("user_password")
        # Get entered username
        usern = request.form.get("username_")
        if password == "1234567" and usern.lower() == "ddlin":
            # Marks users as logged in
            session['login'] = True
            return redirect(url_for("home"))
        else:
            error = "Invalid username or password"  
    return render_template('login.html', error=error)

# Route for adding/updating an expense
@app.route("/add_expense", methods=["GET", "POST"])
def add_expense():
    # Check if user is logged in
    if not session.get('login'):
        # Redirect to login if not
        return redirect('/')

    # If form was submitted
    if request.method == "POST":
        # Get the item ID from the hidden form field
        item_id = request.form.get("item_id")
        # Get the amount entered by the user
        added_val = request.form.get("new_amount")
        # Get today's date as a string
        today = datetime.now().strftime('%Y-%m-%d')

        # Only proceed if a non-empty value was entered
        if added_val and added_val.strip():
            # Open database connection
            conn = get_db()
            # Get the most recent record for this item
            current = conn.execute("""
                SELECT amount FROM expense_records
                WHERE item_id = ?
                ORDER BY record_id DESC LIMIT 1
            """, (item_id,)).fetchone()
            # Use 0 if no record exists yet
            current_amount = current['amount'] if current else 0
            # Add entered value to current running total, never go below 0
            new_amount = max(0, current_amount + float(added_val))

            # Insert a new record (append-only, never update existing rows)
            conn.execute("""
                INSERT INTO expense_records (item_id, amount, date)
                VALUES (?, ?, ?)
            """, (item_id, new_amount, today))
            # Save the new record
            conn.commit()
            # Close the database connection
            conn.close()

        # Redirect back to the edit page
        return redirect(url_for("edit_expenses"))

    # Open database connection (for GET request)
    conn = get_db()
    # Get latest record per item using append-only MAX(record_id) pattern
    rows = conn.execute("""
        SELECT c.name AS category,
               ei.item_id, ei.name AS item_name, ei.type,
               er.amount, er.record_id
        FROM expense_records er
        JOIN expense_items ei ON er.item_id = ei.item_id
        JOIN categories c ON ei.category_id = c.category_id
        WHERE er.record_id IN (
            SELECT MAX(record_id) FROM expense_records GROUP BY item_id
        )
        ORDER BY c.category_id, ei.item_id
    """).fetchall()
    # Close the database connection
    conn.close()

    # Dictionary to group items by category
    all_data = {}
    # Loop through each item
    for row in rows:
        # Get the category name
        cat = row['category']
        # If category not yet in dict, initialise it
        if cat not in all_data:
            all_data[cat] = {'rows': [], 'total': 0}
        # Add item to category
        all_data[cat]['rows'].append(row)
        # Add amount to category total
        all_data[cat]['total'] += row['amount']

    # Render the add expense template
    return render_template('add_expense.html', data=all_data)


# Defines the logout route
@app.route('/logout')
def logout():
    # Clear all session data, effectively logging the user out
    session.clear()
    # Redirect to the login page
    return redirect('/')


# Prints to terminal when app.py is loaded successfully
print("yey")

# Only runs if this file is executed directly (not imported)
if __name__ == "__main__":
    # Start the Flask development server with debug mode on
    app.run(debug=True)