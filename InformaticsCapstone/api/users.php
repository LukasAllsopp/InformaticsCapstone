<?php
// Signup / login for TripCast, backed by the MySQL "users" table.
// Called by auth.js as: api/users.php?action=signup | login | logout | me
session_start();
header('Content-Type: application/json');
require __DIR__ . '/config.php';

function out($code, $data = null) {
    http_response_code($code);
    if ($data !== null) echo json_encode($data);
    exit;
}
function publicUser($row) { // never send the password hash back
    return ['userId' => (int)$row['userId'], 'firstName' => $row['firstName'], 'lastName' => $row['lastName'], 'email' => $row['email']];
}

try {
    $pdo = new PDO($dsn, $dbUser, $dbPass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
    ]);

    $action = $_GET['action'] ?? '';
    $in = json_decode(file_get_contents('php://input'), true) ?: [];
    $method = $_SERVER['REQUEST_METHOD'];

    if ($action === 'signup' && $method === 'POST') {
        $first = trim($in['firstName'] ?? '');
        $last  = trim($in['lastName'] ?? '');
        $email = strtolower(trim($in['email'] ?? ''));
        $pass  = (string)($in['password'] ?? '');

        if ($first === '' || $last === '') out(400, ['error' => 'First and last name are required.']);
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) out(400, ['error' => 'Enter a valid email address.']);
        if (strlen($pass) < 8) out(400, ['error' => 'Password must be at least 8 characters.']);

        $check = $pdo->prepare('SELECT 1 FROM users WHERE email = ?');
        $check->execute([$email]);
        if ($check->fetch()) out(409, ['error' => 'An account with that email already exists.']);

        $insert = $pdo->prepare('INSERT INTO users (firstName, lastName, email, passwordHash) VALUES (?, ?, ?, ?)');
        $insert->execute([$first, $last, $email, password_hash($pass, PASSWORD_DEFAULT)]); // hashed, never plain text
        out(201, ['userId' => (int)$pdo->lastInsertId(), 'firstName' => $first, 'lastName' => $last, 'email' => $email]);
    }

    if ($action === 'login' && $method === 'POST') {
        $email = strtolower(trim($in['email'] ?? ''));
        $pass  = (string)($in['password'] ?? '');
        $stmt = $pdo->prepare('SELECT * FROM users WHERE email = ?');
        $stmt->execute([$email]);
        $row = $stmt->fetch();
        if (!$row || !password_verify($pass, $row['passwordHash'])) {
            out(401, ['error' => 'Invalid credentials. Please try again.']);
        }
        session_regenerate_id(true);
        $_SESSION['userId'] = (int)$row['userId']; // login is kept in a PHP session, not localStorage
        out(200, publicUser($row));
    }

    if ($action === 'logout' && $method === 'POST') {
        session_destroy();
        out(204);
    }

    if ($action === 'me' && $method === 'GET') {
        if (isset($_SESSION['userId'])) {
            $stmt = $pdo->prepare('SELECT * FROM users WHERE userId = ?');
            $stmt->execute([$_SESSION['userId']]);
            if ($row = $stmt->fetch()) out(200, publicUser($row));
        }
        out(401, ['error' => 'Not logged in']);
    }

    out(404, ['error' => 'Unknown action']);
} catch (PDOException $e) {
    error_log('TripCast DB error: ' . $e->getMessage()); // details go to the PHP error log, not the browser
    out(500, ['error' => 'Database error. Check that MySQL is running and api/config.php is correct.']);
}
