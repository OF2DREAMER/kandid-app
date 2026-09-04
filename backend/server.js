const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' })); // Large images/audio base64 data handle karne ke liye

// Static frontend files serve karne ke liye
app.use(express.static(path.join(__dirname)));

// In-Memory Database (Aap ise baad mein MongoDB ya PostgreSQL se replace kar sakte hain)
let database = {
    users: [],
    moments: [],
    messages: {}
};

// 1. Register / Onboarding API
app.post('/api/register', (req, res) => {
    const { name, handle, campus } = req.body;
    const user = {
        id: 'u_' + Date.now(),
        name,
        handle: handle.replace('@', ''),
        campus: campus || 'North City University',
        streak: 1,
        momentCount: 0,
        memoryCount: 0
    };
    database.users.push(user);
    res.json({ success: true, token: 'token_' + user.handle + '_prod', user });
});

// 2. Get Feed Moments API
app.get('/api/feed', (req, res) => {
    res.json({ success: true, feed: database.moments });
});

// 3. Capture & Publish Moment API
app.post('/api/moments/capture', (req, res) => {
    const moment = {
        id: 'post_' + Date.now(),
        ...req.body,
        timeAgo: 'JUST NOW'
    };
    database.moments.unshift(moment);
    res.json({ success: true, message: 'Moment saved successfully', moment });
});

// 4. User Profile & Memories API
app.get('/api/me', (req, res) => {
    const defaultUser = database.users[0] || {
        id: 'u_casey',
        name: 'Casey Rhodes',
        handle: 'casey.rx',
        campus: 'Central Campus',
        streak: 12,
        momentCount: database.moments.length,
        memoryCount: database.moments.length
    };
    res.json({ success: true, user: defaultUser });
});

app.get('/api/me/moments', (req, res) => {
    res.json({ success: true, moments: database.moments });
});

app.get('/api/me/memories', (req, res) => {
    res.json({ success: true, count: database.moments.length, moments: database.moments });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Kandid Live Server running on port ${PORT}`);
});