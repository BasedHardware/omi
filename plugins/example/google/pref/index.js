const express = require('express');
const bodyParser = require('body-parser');

const app = express(); 

app.use(express.json());
app.use(bodyParser.urlencoded({ extended: true }));

app.listen(3000 , () => {
    console.log('Server is running on port 3000');
});

app.get('/page' , function(req,res) {
    res.sendFile(__dirname + '/index.html');
})

userData = []

app.post('/user_preferences' , function(req,res){
    data = req.body.options;
    pref = JSON.stringify(data);
    userData.push(pref);
})

app.get('/user_preferences' , function(req,res){
    res.send(userData);
});