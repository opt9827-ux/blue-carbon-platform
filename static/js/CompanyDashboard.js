// Company Dashboard Logic
console.log("Company Dashboard Loaded");

function buyCredit(id) {
    if(confirm("Confirm purchase of credits #" + id + "?")) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/buy_credits/' + id;
        document.body.appendChild(form);
        form.submit();
    }
}
