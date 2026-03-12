const ICONS = [
'apple','apricot','banana','big_win','cherry','grapes','lemon',
'lucky_seven','orange','pear','strawberry','watermelon'
];

const BASE_SPINNING_DURATION = 2.7;
const COLUMN_SPINNING_DURATION = 0.3;

let cols;

window.addEventListener('DOMContentLoaded', function () {

    cols = document.querySelectorAll('.col');

    setInitialItems();

});


function setInitialItems(){

    let baseItemAmount = 40;

    for(let i=0;i<cols.length;i++){

        let col = cols[i];

        let amount = baseItemAmount + (i*3);

        let html = "";
        let firstThree = "";

        for(let x=0;x<amount;x++){

            let icon = getRandomIcon();

            let item =
            `<div class="icon">
            <img src="/static/items/${icon}.png">
            </div>`;

            html += item;

            if(x<3) firstThree += item;

        }

        col.innerHTML = html + firstThree;

    }

}


function spin(button){

    let duration = BASE_SPINNING_DURATION + randomDuration();

    for(let col of cols){

        duration += COLUMN_SPINNING_DURATION + randomDuration();

        col.style.animationDuration = duration + "s";

    }

    button.setAttribute("disabled",true);

    document.getElementById("container").classList.add("spinning");

    setTimeout(()=>{

        requestResult();

    },BASE_SPINNING_DURATION*500);

    setTimeout(()=>{

        document.getElementById("container").classList.remove("spinning");

        button.removeAttribute("disabled");

    },duration*1000);

}


function requestResult(){

    let aposta = document.getElementById("aposta").value;

    fetch("/api/spin",{
        method:"POST",
        headers:{
            "Content-Type":"application/json"
        },
        body:JSON.stringify({
            aposta:aposta
        })
    })
    .then(res=>res.json())
    .then(data=>{

        setResult(data.resultado);

        document.getElementById("saldo").innerText = data.saldo;

        if(data.ganho>0){

            alert("🎉 Você ganhou R$ "+data.ganho);

        }

    })
    .catch(()=>{

        console.log("erro slot");

    });

}


function setResult(serverResult){

    for(let col of cols){

        let results = serverResult || [
            getRandomIcon(),
            getRandomIcon(),
            getRandomIcon()
        ];

        let icons = col.querySelectorAll(".icon img");

        for(let x=0;x<3;x++){

            icons[x].src = "/static/items/"+results[x]+".png";

            icons[(icons.length-3)+x].src = "/static/items/"+results[x]+".png";

        }

    }

}


function getRandomIcon(){

    return ICONS[Math.floor(Math.random()*ICONS.length)];

}


function randomDuration(){

    return Math.floor(Math.random()*10)/100;

}
