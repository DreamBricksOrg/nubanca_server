const btn_termos = document.getElementById("aceito_termos");
localStorage.clear();
btn_termos.addEventListener("click", () => {
  window.location.href = BASE_URL + "/validacao";
});
