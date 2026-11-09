<?php
// Save and list trips for the logged-in user.
//   POST api/trips.php?action=save   body: { tripName, destinations: [{ name, latitude, longitude, weather }] }
//   GET  api/trips.php?action=list
session_start();
header('Content-Type: application/json');
require __DIR__ . '/config.php';

function out($code, $data = null) {
    http_response_code($code);
    if ($data !== null) echo json_encode($data);
    exit;
}
function cut($s, $n) { return function_exists('mb_substr') ? mb_substr($s, 0, $n) : substr($s, 0, $n); }
function inRange($v, $min, $max) { return is_numeric($v) && $v >= $min && $v <= $max; }
function numOrNull($v) { return (isset($v) && is_numeric($v)) ? (float)$v : null; }

// The user always comes from the session, never from anything the page sends.
if (!isset($_SESSION['userId'])) out(401, ['error' => 'Please log in first.']);
$userId = (int)$_SESSION['userId'];

try {
    $pdo = new PDO($dsn, $dbUser, $dbPass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
    ]);
    $action = $_GET['action'] ?? '';
    $method = $_SERVER['REQUEST_METHOD'];

    if ($action === 'save' && $method === 'POST') {
        $in = json_decode(file_get_contents('php://input'), true) ?: [];
        $tripName = cut(trim((string)($in['tripName'] ?? '')), 100);
        if ($tripName === '') $tripName = 'My trip';

        $dests = $in['destinations'] ?? null;
        if (!is_array($dests) || count($dests) < 1) out(400, ['error' => 'Add at least one destination.']);
        if (count($dests) > 50) out(400, ['error' => 'A trip can have at most 50 destinations.']);

        $clean = [];
        foreach (array_values($dests) as $d) {
            $name = cut(trim((string)($d['name'] ?? '')), 255);
            if ($name === '') out(400, ['error' => 'Every destination needs a name.']);
            if (!inRange($d['latitude'] ?? null, -90, 90) || !inRange($d['longitude'] ?? null, -180, 180)) {
                out(400, ['error' => 'A destination has invalid coordinates.']);
            }
            $w = null;
            if (isset($d['weather']) && is_array($d['weather'])) {
                $hum = numOrNull($d['weather']['humidity'] ?? null);
                $w = [
                    'temperature' => numOrNull($d['weather']['temperature'] ?? null),
                    'condition'   => cut((string)($d['weather']['condition'] ?? ''), 60),
                    'humidity'    => $hum === null ? null : (int)max(0, min(100, round($hum))),
                    'windSpeed'   => numOrNull($d['weather']['windSpeed'] ?? null),
                ];
            }
            $clean[] = ['name' => $name, 'lat' => (float)$d['latitude'], 'lng' => (float)$d['longitude'], 'weather' => $w];
        }

        // Either the whole trip is saved or none of it is.
        $pdo->beginTransaction();
        $pdo->prepare('INSERT INTO trips (userId, tripName) VALUES (?, ?)')->execute([$userId, $tripName]);
        $tripId = (int)$pdo->lastInsertId();
        $insDest = $pdo->prepare('INSERT INTO destinations (userId, tripId, locationName, latitude, longitude, stopOrder) VALUES (?, ?, ?, ?, ?, ?)');
        $insWx = $pdo->prepare('INSERT INTO weather_snapshots (destinationId, temperature, weatherCondition, humidity, windSpeed) VALUES (?, ?, ?, ?, ?)');
        foreach ($clean as $i => $d) {
            $insDest->execute([$userId, $tripId, $d['name'], $d['lat'], $d['lng'], $i + 1]);
            if ($d['weather'] !== null) {
                $destId = (int)$pdo->lastInsertId();
                $w = $d['weather'];
                $insWx->execute([$destId, $w['temperature'], $w['condition'] === '' ? null : $w['condition'], $w['humidity'], $w['windSpeed']]);
            }
        }
        $pdo->commit();
        out(201, ['tripId' => $tripId]);
    }

    if ($action === 'list' && $method === 'GET') {
        $stmt = $pdo->prepare('SELECT tripId, tripName, createdAt FROM trips WHERE userId = ? ORDER BY createdAt DESC, tripId DESC');
        $stmt->execute([$userId]);
        $trips = [];
        foreach ($stmt->fetchAll() as $t) {
            $trips[(int)$t['tripId']] = ['tripId' => (int)$t['tripId'], 'tripName' => $t['tripName'], 'createdAt' => $t['createdAt'], 'destinations' => []];
        }

        // Each destination with its most recent saved weather reading.
        $stmt = $pdo->prepare(
            'SELECT d.destinationId, d.tripId, d.locationName, d.latitude, d.longitude, d.stopOrder,
                    w.temperature, w.weatherCondition, w.humidity, w.windSpeed, w.fetchedAt
             FROM destinations d
             LEFT JOIN weather_snapshots w
               ON w.snapshotId = (SELECT MAX(snapshotId) FROM weather_snapshots WHERE destinationId = d.destinationId)
             WHERE d.userId = ? AND d.tripId IS NOT NULL
             ORDER BY d.tripId, d.stopOrder'
        );
        $stmt->execute([$userId]);
        foreach ($stmt->fetchAll() as $d) {
            $hasWeather = $d['fetchedAt'] !== null;
            $trips[(int)$d['tripId']]['destinations'][] = [
                'destinationId' => (int)$d['destinationId'],
                'locationName'  => $d['locationName'],
                'latitude'      => (float)$d['latitude'],
                'longitude'     => (float)$d['longitude'],
                'order'         => (int)$d['stopOrder'],
                'weather'       => $hasWeather ? [
                    'temperature' => $d['temperature'] === null ? null : (float)$d['temperature'],
                    'condition'   => $d['weatherCondition'],
                    'humidity'    => $d['humidity'] === null ? null : (int)$d['humidity'],
                    'windSpeed'   => $d['windSpeed'] === null ? null : (float)$d['windSpeed'],
                    'fetchedAt'   => $d['fetchedAt'],
                ] : null,
            ];
        }
        out(200, ['trips' => array_values($trips)]);
    }

    out(404, ['error' => 'Unknown action']);
} catch (PDOException $e) {
    if (isset($pdo) && $pdo->inTransaction()) $pdo->rollBack();
    error_log('TripCast trips error: ' . $e->getMessage()); // details go to the PHP error log, not the browser
    out(500, ['error' => 'Database error. Did you run 002_add_trips.sql? Check the PHP error log for details.']);
}
