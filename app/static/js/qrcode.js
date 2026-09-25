let qr = document.getElementById("qrcode");
let back_button = document.getElementById("back_button");
let linkImage = localStorage.getItem("qrcodeImagePath");

var qrcode = new QRCode(qr, {
  text: linkImage,
  colorDark: "#ffffff",
  colorLight: "#8D0DE3",
  width: 480,
  height: 480,
});


function retornarTermos(){
    window.location.href = BASE_URL + "/";
}

setTimeout(retornarTermos, TIMEOUT * 1000);
