const content = document.getElementById("content");
const disapproved_btn = document.getElementById("disapproved");
const approved_btn = document.getElementById("approved");
let footer = document.getElementById("footer_buttons");
footer.style.display = "none";

async function obterFotoMaisRecente() {
  try {
    const resposta = await fetch(BASE_URL + "/image");
    if (!resposta.ok) {
      throw new Error("Erro na requisição: " + resposta.status);
    }

    const dados = await resposta.json();
    let img = document.createElement("img");
    img.classList.add("img_captured");
    img.src = dados.image_url;
    content.appendChild(img);
    footer.style.display = "flex";
    document.getElementById("loading").style.display = "none";
  } catch (error) {
    console.log(error);
    setTimeout(obterFotoMaisRecente, timer_pooling * 1000);
  }
}

async function descartar() {
  try {
    const options = {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    };
    const resposta = await fetch(BASE_URL + "/discard", options);
    const dados = await resposta.json();
    let img = document.getElementsByClassName("img_captured")[0];
    img.remove();
    console.log(dados);
    footer.style.display = "none";
    document.getElementById("loading").style.display = "flex";
    setTimeout(obterFotoMaisRecente, timer_pooling);
  } catch (error) {
    console.log(error);
  }
}

obterFotoMaisRecente();

approved_btn.addEventListener("click", async () => {
  let img = document.getElementsByClassName("img_captured")[0];
  localStorage.setItem("imgData", img.src);
  window.location.href = BASE_URL + "/editor";
});
disapproved_btn.addEventListener("click", async () => {
  await descartar();
});
