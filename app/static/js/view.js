(function () {
  "use strict";

  var splash = document.getElementById("splash");
  var video = document.getElementById("splash-video");
  var content = document.getElementById("content");
  var photo = document.getElementById("photo");
  var photoError = document.getElementById("photo-error");

  var MIN_SPLASH_MS = 900;
  var MAX_WAIT_MS = 6000;

  var introPlaying = true;
  var photoSettled = false;
  var photoOk = false;
  var minTimeDone = false;
  var revealed = false;

  function maybeReveal() {
    if (revealed || introPlaying || !photoSettled || !minTimeDone) {
      return;
    }
    revealed = true;
    video.loop = false;
    video.src = video.dataset.out;
    video.onended = finishReveal;
    video.play().catch(finishReveal);
  }

  function finishReveal() {
    if (content.classList.contains("hidden") === false) {
      return;
    }
    splash.classList.add("splash-hidden");
    content.classList.remove("hidden");
    if (!photoOk) {
      photo.classList.add("hidden");
      photoError.classList.remove("hidden");
    }
  }

  video.addEventListener("ended", function onIntroEnded() {
    if (!introPlaying) {
      return;
    }
    introPlaying = false;
    video.removeEventListener("ended", onIntroEnded);
    video.loop = true;
    video.src = video.dataset.loop;
    video.play().catch(function () {});
    maybeReveal();
  });

  function settlePhoto(ok) {
    photoOk = ok;
    photoSettled = true;
    maybeReveal();
  }

  if (photo.complete) {
    settlePhoto(photo.naturalWidth > 0);
  } else {
    photo.addEventListener("load", function () {
      settlePhoto(true);
    });
    photo.addEventListener("error", function () {
      settlePhoto(false);
    });
  }

  setTimeout(function () {
    minTimeDone = true;
    maybeReveal();
  }, MIN_SPLASH_MS);

  setTimeout(function () {
    introPlaying = false;
    minTimeDone = true;
    photoSettled = true;
    maybeReveal();
  }, MAX_WAIT_MS);

  video.src = video.dataset.in;
  video.play().catch(function () {
    introPlaying = false;
    maybeReveal();
  });

  var shareBtn = document.getElementById("share-btn");
  shareBtn.addEventListener("click", function () {
    var imageUrl = photo.dataset.src;
    var pageUrl = window.location.href;

    function shareUrlFallback() {
      if (navigator.share) {
        navigator.share({ title: "Minha foto", url: pageUrl }).catch(function () {});
        return;
      }
      if (navigator.clipboard) {
        navigator.clipboard.writeText(pageUrl).then(function () {
          alert("Link copiado!");
        }).catch(function () {
          alert(pageUrl);
        });
      } else {
        alert(pageUrl);
      }
    }

    if (!navigator.canShare) {
      shareUrlFallback();
      return;
    }

    fetch(imageUrl)
      .then(function (response) {
        return response.blob();
      })
      .then(function (blob) {
        var file = new File([blob], "foto.jpg", { type: blob.type || "image/jpeg" });
        if (navigator.canShare({ files: [file] })) {
          return navigator.share({ files: [file], title: "Minha foto" });
        }
        shareUrlFallback();
      })
      .catch(shareUrlFallback);
  });
})();
