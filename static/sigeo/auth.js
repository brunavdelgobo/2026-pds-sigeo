const authCard = document.getElementById('authCard');
const btnToLogin = document.getElementById('btnToLogin');
const btnToCadastro = document.getElementById('btnToCadastro');

if (btnToCadastro && btnToLogin && authCard) {
    btnToCadastro.addEventListener('click', () => {
        authCard.classList.remove('login-active');
        authCard.classList.add('cadastro-active');
    });

    btnToLogin.addEventListener('click', () => {
        authCard.classList.remove('cadastro-active');
        authCard.classList.add('login-active');
    });
}