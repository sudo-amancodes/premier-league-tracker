CREATE DATABASE uspc_swe_project;

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    profile_picture VARCHAR(255), 
    PRIMARY KEY (user_id)
);
CREATE TABLE IF NOT EXISTS soccer_teams (
    team_id SERIAL,
    team_name VARCHAR(255) NOT NULL,
    wins_draws_losses VARCHAR(50),
    logo VARCHAR(255),
    PRIMARY KEY (team_id)
);

CREATE TABLE IF NOT EXISTS user_watchlist_teams (
    user_id INT REFERENCES users(user_id),
    team_id INT REFERENCES soccer_teams(team_id),
    PRIMARY KEY (user_id, team_id)
);
