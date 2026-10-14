// Plain-JS port of PrairieLearn's assets/scripts/examTimeLimitCountdown.ts and
// assets/scripts/lib/countdown.ts (AGPL-3.0, see LICENSE-PrairieLearn.txt).
(function () {
  function showWarningPopup(id, message) {
    let popup = document.querySelector('#warning-popup');
    if (!popup) {
      popup = document.createElement('div');
      popup.id = 'warning-popup';
      popup.className = 'fixed-bottom d-flex flex-column align-items-center mb-5';
      document.body.append(popup);
    }
    if (!document.querySelector('#popup-' + id)) {
      const div = document.createElement('div');
      div.id = 'popup-' + id;
      div.className = 'show align-items-center alert alert-warning alert-dismissible pulse';
      div.setAttribute('role', 'alert');
      div.innerHTML =
        '<div></div><button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
      div.firstChild.textContent = message;
      popup.append(div);
    }
  }

  function setupCountdown(options) {
    const countdownDisplay = document.querySelector(options.displaySelector);
    const countdownProgress = document.querySelector(options.progressSelector);
    if (!countdownDisplay || !countdownProgress) return;

    let serverRemainingMS, serverTimeLimitMS, clientStart;
    let lastRemainingMS = options.initialServerRemainingMS;
    let updateServerIfExpired = true;
    let nextTimeout = null;

    countdownProgress.classList.add('progress');
    countdownProgress.innerHTML = '<div class="progress-bar bg-primary"></div>';
    const bar = countdownProgress.querySelector('div');

    function handle(data) {
      serverRemainingMS = data.serverRemainingMS;
      serverTimeLimitMS = data.serverTimeLimitMS;
      clientStart = Date.now();
      if (serverRemainingMS <= 0) {
        options.onTimerOut();
        updateServerIfExpired = false;
      } else {
        display();
      }
    }

    function update() {
      fetch(options.serverUpdateURL)
        .then((r) => r.json())
        .then(handle)
        .catch(() => {
          const remainingMS = Math.max(0, serverRemainingMS - (Date.now() - clientStart));
          options.onServerUpdateFail(remainingMS);
          if (remainingMS <= 0) updateServerIfExpired = false;
          display();
        });
    }

    function display() {
      const remainingMS = Math.max(0, serverRemainingMS - (Date.now() - clientStart));
      const remainingSec = Math.floor(remainingMS / 1000);
      const remainingMin = Math.floor(remainingSec / 60);
      const perc = 100 - Math.max(0, Math.min(100, (remainingMS / serverTimeLimitMS) * 100));
      bar.style.width = perc + '%';
      bar.className = 'progress-bar ' + options.getBackgroundColor(remainingSec);
      countdownDisplay.innerText = remainingSec >= 60 ? remainingMin + ' min' : remainingSec + ' sec';
      if (remainingMS > 0) {
        for (const t in options.onRemainingTime) {
          if (remainingMS <= +t && +t < lastRemainingMS) options.onRemainingTime[t]();
        }
        lastRemainingMS = remainingMS;
        if (nextTimeout != null) clearTimeout(nextTimeout);
        nextTimeout = setTimeout(display, (remainingMS - 500) % 1000);
      } else if (updateServerIfExpired) {
        update();
      } else {
        options.onTimerOut();
      }
    }

    handle({
      serverRemainingMS: options.initialServerRemainingMS,
      serverTimeLimitMS: options.initialServerTimeLimitMS,
    });
    setInterval(update, 60000);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById('time-limit-data');
    if (!el) return;
    const data = JSON.parse(el.textContent);
    setupCountdown({
      displaySelector: '#countdownDisplay',
      progressSelector: '#countdownProgress',
      initialServerRemainingMS: data.serverRemainingMS,
      initialServerTimeLimitMS: data.serverTimeLimitMS,
      serverUpdateURL: data.serverUpdateURL,
      onTimerOut: () => {
        const countdown = document.querySelector('#countdownDisplay');
        if (countdown) countdown.innerHTML = 'expired';
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = data.finishURL;
        form.innerHTML = '<input type="hidden" name="__action" value="timeLimitFinish" />';
        document.body.append(form);
        form.submit();
      },
      onRemainingTime: {
        60000: () =>
          showWarningPopup('examTimeout', 'Your exam is ending soon. Please finish and submit your work.'),
      },
      onServerUpdateFail: () => window.location.reload(),
      getBackgroundColor: (remainingSec) =>
        remainingSec >= 180 ? 'bg-primary' : remainingSec >= 60 ? 'bg-warning' : 'bg-danger',
    });
  });
})();
