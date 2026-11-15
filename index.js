/******** INNOVEX PAY ANONYMOUS BOT ********/


const BOT_TOKEN = "9194760036:AAEtiReEe43mtbR3LGaD8UU8KDF8QfruclQ";

const GROUP_ID = "1004378570213";

const ADMIN_IDS = [5673859926];


/******** TELEGRAM API ********/


function telegram(method, data) {

  const url = "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method;


  const response = UrlFetchApp.fetch(url, {

    method: "post",

    contentType: "application/json",

    payload: JSON.stringify(data || {}),

    muteHttpExceptions: true

  });


  const result = JSON.parse(response.getContentText());


  if (!result.ok) {

    throw new Error(result.description);

  }


  return result.result;

}


/******** SEND MESSAGE ********/


function sendMessage(chatId, text, keyboard) {

  const data = {

    chat_id: chatId,

    text: text

  };


  if (keyboard) {

    data.reply_markup = keyboard;

  }


  return telegram("sendMessage", data);

}


/******** BOT SETUP ********/


function setupBot() {

  telegram("deleteWebhook", {

    drop_pending_updates: false

  });


  ScriptApp.getProjectTriggers().forEach(trigger => {

    if (trigger.getHandlerFunction() === "checkUpdates") {

      ScriptApp.deleteTrigger(trigger);

    }

  });


  ScriptApp.newTrigger("checkUpdates")

    .timeBased()

    .everyMinutes(1)

    .create();


  Logger.log("INNOVEX PAY BOT SETUP COMPLETE");

}


/******** CHECK UPDATES ********/


function checkUpdates() {

  const props = PropertiesService.getScriptProperties();

  const offset = Number(props.getProperty("TG_OFFSET") || 0);


  const updates = telegram("getUpdates", {

    offset: offset,

    timeout: 20,

    allowed_updates: ["message", "callback_query"]

  });


  updates.forEach(update => {

    try {

      if (update.message) {

        handleMessage(update.message);

      }


      if (update.callback_query) {

        handleCallback(update.callback_query);

      }


      props.setProperty(

        "TG_OFFSET",

        String(update.update_id + 1)

      );


    } catch (error) {

      console.error(error);

      throw error;

    }

  });

}


/******** RECEIVE MESSAGE ********/


function handleMessage(message) {

  if (!message.chat || message.chat.type !== "private") return;


  const chatId = String(message.chat.id);

  const text = message.text || "";


  if (!text || text.startsWith("/")) {

    return;

  }


  if (ADMIN_IDS.map(String).includes(chatId)) {

    return;

  }


  if (text.length > 3500) {

    sendMessage(chatId, "Message is too long. Please send a shorter message.");

    return;

  }


  const id = Utilities.getUuid().replace(/-/g, "").slice(0, 16);


  const props = PropertiesService.getScriptProperties();


  props.setProperty("PENDING_" + id, JSON.stringify({

    text: text,

    status: "pending"

  }));


  const keyboard = {

    inline_keyboard: [[

      {

        text: "✅ ACCEPT",

        callback_data: "a:" + id

      },

      {

        text: "❌ REJECT",

        callback_data: "r:" + id

      }

    ]]

  };


  ADMIN_IDS.forEach(adminId => {

    sendMessage(

      adminId,

      "📩 NEW ANONYMOUS MESSAGE\n\n" + text,

      keyboard

    );

  });


  sendMessage(chatId, "✅ Your message has been submitted for review.");

}


/******** ADMIN APPROVAL ********/


function handleCallback(query) {

  const adminId = String(query.from.id);


  if (!ADMIN_IDS.map(String).includes(adminId)) {

    telegram("answerCallbackQuery", {

      callback_query_id: query.id,

      text: "Not authorized."

    });

    return;

  }


  const parts = query.data.split(":");

  const action = parts[0];

  const id = parts[1];


  const lock = LockService.getScriptLock();

  lock.waitLock(10000);


  try {

    const props = PropertiesService.getScriptProperties();

    const key = "PENDING_" + id;

    const raw = props.getProperty(key);


    if (!raw) {

      telegram("answerCallbackQuery", {

        callback_query_id: query.id,

        text: "Message not found."

      });

      return;

    }


    const item = JSON.parse(raw);


    if (item.status !== "pending") {

      telegram("answerCallbackQuery", {

        callback_query_id: query.id,

        text: "Already processed."

      });

      return;

    }


    if (action === "a") {

      telegram("sendMessage", {

        chat_id: GROUP_ID,

        text: "📩 Anonymous Message\n\n" + item.text

      });


      item.status = "approved";


    } else if (action === "r") {

      item.status = "rejected";


    } else {

      return;

    }


    props.setProperty(key, JSON.stringify(item));


    telegram("editMessageText", {

      chat_id: query.message.chat.id,

      message_id: query.message.message_id,

      text: "Message " + item.status.toUpperCase() + "\n\n" + item.text

    });


    telegram("answerCallbackQuery", {

      callback_query_id: query.id,

      text: "Done!"

    });


  } finally {

    lock.releaseLock();

  }

}