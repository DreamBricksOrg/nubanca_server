const content = document.getElementById("content");
const disapproved_btn = document.getElementById("disapproved");
async function obterFotoMaisRecente() {
  try {
    const resposta = await fetch("http://127.0.0.1:5000/image");
    if (!resposta.ok) {
      throw new Error("Erro na requisição: " + resposta.status);
    }

    const dados = await resposta.json();
    let img = document.createElement("img");
    img.classList.add("img_captured");
    img.src = dados.image_url;
    content.appendChild(img);
  } catch (error) {
    console.log(error);
    setTimeout(obterFotoMaisRecente, 15000);
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
    const resposta = await fetch("http://127.0.0.1:5000/discard", options);
    const dados = await resposta.json();
    let img = document.getElementsByClassName("img_captured")[0];
    img.remove();
    console.log(dados);
  } catch (error) {
    console.log(error);
  } finally {
    setTimeout(obterFotoMaisRecente, 15000);
  }
}

obterFotoMaisRecente();
disapproved_btn.addEventListener("click", async () => {
  await descartar();
});
