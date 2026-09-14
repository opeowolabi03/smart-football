SMART FOOTBALL
README

Project Title
Smart Football: A Data-Driven Approach to Fair Match Organisation for Communities

Author
Deborah Owolabi

Project Overview
Smart Football is a Django-based web application designed to support community football organisation. The system allows users to register, manage player profiles, view and join football sessions, track attendance, generate balanced teams, and review match or dashboard information.

The project focuses on making small-scale football organisation fairer and more efficient by replacing informal manual organisation with a structured web platform. Organisers can create sessions, manage players, record attendance, and generate teams using player profile information such as skill level, fitness level, preferred position, and experience.
GitHub repository: https://github.com/opeowolabi03/smart-football
But can download the zip folder and run on VSCode

Main Features
- User registration, login, and logout using Django authentication.
- Player and organiser roles using a Profile model.
- Player profile editing for skill level, fitness level, position preference, and experience.
- Match session creation with title, date/time, location, capacity, and organiser information.
- Session list page showing available football sessions.
- Match detail page showing session information, participants, attendance, and generated teams.
- Join session functionality for authenticated users.
- Leave session functionality for users who have already joined.
- Capacity checking to prevent users joining full sessions.
- Attendance tracking, allowing organisers to mark players as attended or not attended.
- Organiser dashboard showing sessions created by the organiser, participant totals, and attendance totals.
- Team allocation using player profile data to divide players into Team A and Team B.
- Rating model for peer feedback after sessions.
- Basic dashboard/statistics support using Django queries and Chart.js where included in the frontend.
- Demo seed data support where optional seed scripts are included.

Technology Stack
- Python
- Django
- SQLite
- HTML
- CSS
- JavaScript
- Chart.js
- Git
- VS Code

Project Structure
The project uses a standard Django structure:

smart-football/
  manage.py
  config/
    settings.py
    urls.py
  accounts/
    models.py
    views.py
    forms.py
    urls.py
    signals.py
    apps.py
  scheduling/
    models.py
    views.py
    urls.py
    admin.py
  templates/
    base.html
    accounts/
    registration/
    scheduling/
  static/
    css/
      smartfootball.css
  db.sqlite3

Key Apps

accounts
The accounts app handles authentication and user profile functionality. It includes login, logout, signup, role handling, and profile editing.

Main account features:
- User signup
- User login/logout
- Player and organiser role storage
- Automatic profile creation using Django signals
- Profile editing form

scheduling
The scheduling app handles football sessions, participation, attendance, ratings, team generation, and organiser dashboard views.

Main scheduling features:
- MatchSession model
- Participation model
- Rating model
- TeamAssignment model
- Session list view
- Session detail view
- Session creation view
- Join/leave session views
- Attendance toggle view
- Team generation view
- Organiser dashboard view

Core Models

Profile
Stores extra user information beyond Django's built-in User model.

Main fields:
- user
- role
- skill_level
- fitness_level
- position_preference
- experience

MatchSession
Stores information about a football session.

Main fields:
- title
- start_datetime
- location
- capacity
- created_by

Participation
Links users to match sessions and stores attendance status.

Main fields:
- session
- user
- attended

Rating
Stores player feedback and session-related ratings.

Main fields:
- session
- rater
- ratee
- score
- comment
- created_at

TeamAssignment
Stores which generated team each player belongs to.

Main fields:
- session
- user
- team
- created_at

Installation Instructions

1. Clone or download the project folder.

2. Open the project folder in VS Code.

3. Open a terminal inside the project folder.

4. Create a virtual environment:

   python -m venv .venv

5. Activate the virtual environment on Windows:

   .venv\Scripts\activate

   If PowerShell blocks activation, run:

   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

   Then close and reopen the terminal before activating the environment again.

6. Upgrade pip:

   python -m pip install --upgrade pip

7. Install Django:

   pip install django

   If the project includes a requirements.txt file, use this instead:

   pip install -r requirements.txt

8. Run migrations:

   python manage.py makemigrations
   python manage.py migrate

9. Create an admin user:

   python manage.py createsuperuser

10. Run the development server:

   python manage.py runserver

11. Open the application in a browser:

   http://127.0.0.1:8000/

Logins:
Organiser
user: organiser_james
password: password123

Player
user:amelia_brown 
password: password123

For more look in report or login guide in folder

Common URLs

Home / Player dashboard:
http://127.0.0.1:8000/

All sessions:
http://127.0.0.1:8000/sessions/

Create session:
http://127.0.0.1:8000/create/

Organiser dashboard:
http://127.0.0.1:8000/organiser/

Login:
http://127.0.0.1:8000/accounts/login/

Signup:
http://127.0.0.1:8000/accounts/signup/

Edit profile:
http://127.0.0.1:8000/accounts/profile/

Admin panel:
http://127.0.0.1:8000/admin/

How to Use the System

Player workflow
1. Register or log in.
2. Edit the player profile by entering skill level, fitness level, preferred position, and experience.
3. View available sessions.
4. Join a session that is not full.
5. Leave the session if needed.
6. View match details and team allocation once generated.
7. Rate other players after a session where rating functionality is available.

Organiser workflow
1. Log in using an organiser account or staff account.
2. Create a match session by entering the title, date/time, location, and capacity.
3. View the organiser dashboard.
4. Open a session detail page.
5. Review the participant list.
6. Mark attendance for players.
7. Generate teams for the session.
8. Review Team A and Team B allocations.
9. Use dashboard information to review attendance and session activity.

Team Allocation Logic
The team allocation feature uses player profile data to create balanced teams. The documented score calculation uses player attributes such as skill level, fitness level, and experience. Players are sorted by score and then assigned to Team A or Team B to keep the total team scores as balanced as possible.

This approach is designed for a small community football prototype where team generation needs to be fast, understandable, and easy to demonstrate.

Testing Checklist
The following checks can be used to test the system:

Authentication
- A new user can sign up.
- A user can log in.
- A user can log out.
- A logged-out user is redirected where login is required.

Profile
- A user can access the profile page.
- A user can update skill level, fitness level, position preference, and experience.
- Profile information is saved correctly.

Sessions
- A session can be created by an organiser.
- Sessions appear in the session list.
- A session detail page displays the correct title, date/time, location, and capacity.
- A player can join a session.
- A player can leave a session.
- A full session cannot be joined.

Attendance
- The organiser can mark a participant as attended.
- The organiser can mark a participant as not attended.
- Non-organisers cannot mark attendance.

Team Allocation
- Teams can be generated when enough players have joined.
- Team assignments are saved.
- Team A and Team B display on the session detail page.
- Regenerating teams updates the existing allocation.

Dashboard
- The organiser dashboard displays sessions created by the organiser.
- Joined player counts are shown.
- Attendance totals are shown.

Development Notes
- The application uses SQLite for local development.
- The db.sqlite3 file should normally not be committed to Git unless specifically required for demonstration.
- The .venv folder should not be committed.
- Static files are stored in the static folder.
- HTML templates are stored in the templates folder.
- The frontend styling uses the Smart Football colour scheme with green, navy, lime, white, and grey dashboard-style components.

Known Limitations
- The system is a local academic prototype and is not configured for production deployment.
- SQLite is suitable for development but should be replaced with a production database for real deployment.
- The fairness algorithm is intentionally simple and explainable rather than a machine learning model.
- Player skill values are based on profile/self-assessment and optional feedback, so accuracy depends on the quality of user input.
- Payment handling is outside the project scope.
- The system should be tested with prepared demo data before assessment or presentation.

Suggested Future Improvements
- Add email verification for new accounts.
- Add password reset functionality.
- Add match result recording and match history pages if not already enabled.
- Add more detailed fairness metrics and visual charts.
- Add notifications for upcoming sessions.
- Add organiser controls for editing or cancelling sessions.
- Improve mobile responsiveness further.
- Add deployment configuration for a live server.

Git Commands

Check current changes:

git status

Stage all changes:

git add .

Commit changes:

git commit -m "Update Smart Football project"

Push to GitHub:

git push

If GitHub rejects the push because the remote contains changes, run:

git pull --rebase origin main
git push

Academic Context
This project was developed as part of the 6CM995 Individual Project. The system demonstrates practical software development using Django and supports the dissertation objectives of authentication, scheduling, attendance tracking, team balancing, dashboard/statistical review, and evaluation of fairness and usability.
