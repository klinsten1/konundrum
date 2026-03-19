document.getElementById('loginForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    // Basic validation
    if (username.trim() === '' || password.trim() === '') {
        alert('Please fill in all fields');
        return;
    }
    
    if (password.length < 6) {
        alert('Password must be at least 6 characters');
        return;
    }
    
    // Here you would send the login data to your backend
    console.log('Login attempt:', { username, password });
    alert('Login successful! (Demo mode)');
    
    // Reset form
    this.reset();
});
